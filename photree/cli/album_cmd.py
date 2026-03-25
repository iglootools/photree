"""CLI commands for the ``photree album`` sub-app."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Optional

import typer

from ..album import (
    ios_fixes,
    naming as album_naming,
    optimize as album_optimize,
    output as album_output,
    preflight as album_preflight,
)
from ..album.exif import check_exiftool_available
from ..fsprotocol import (
    MAIN_IMG_DIR,
    IMG_EXTENSIONS,
    LinkMode,
    MOV_EXTENSIONS,
    ORIG_IMG_DIR,
    ORIG_VID_DIR,
    display_path,
    list_files,
)
from .progress import FileProgressBar, SilentProgressBar, StageProgressBar

album_app = typer.Typer(
    name="album",
    help="Album management commands.",
    no_args_is_help=True,
)


@album_app.command("check")
def check_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to check.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    checksum: Annotated[
        bool,
        typer.Option(
            "--checksum/--no-checksum",
            help="Enable/disable SHA-256 checksum verification (default: enabled).",
        ),
    ] = True,
    fatal_warnings: Annotated[
        bool,
        typer.Option(
            "--fatal-warnings",
            "-W",
            help="Treat informational warnings (e.g. missing sidecars) as errors.",
        ),
    ] = False,
    check_naming: Annotated[
        bool,
        typer.Option(
            "--check-naming/--no-check-naming",
            help="Enable/disable album naming convention checks (default: enabled).",
        ),
    ] = True,
) -> None:
    """Check system prerequisites, album directory structure, and file integrity."""
    # Count unique media numbers in orig dirs — the integrity check fires one
    # callback per expected main file, which is one per orig media number.
    file_count = _count_unique_media_numbers(
        album_dir / ORIG_IMG_DIR, IMG_EXTENSIONS
    ) + _count_unique_media_numbers(album_dir / ORIG_VID_DIR, MOV_EXTENSIONS)
    progress = (
        SilentProgressBar(total=max(file_count, 1), description="Checking")
        if file_count > 0
        else None
    )

    result = album_preflight.run_album_preflight(
        album_dir,
        checksum=checksum,
        check_naming_flag=check_naming,
        on_file_checked=progress.advance if progress else None,
    )
    if progress:
        progress.stop()

    typer.echo(album_output.format_album_preflight_checks(result))

    failed = not result.success or (fatal_warnings and result.has_warnings)
    if failed:
        cwd = Path.cwd()
        troubleshoot = album_output.format_album_preflight_troubleshoot(
            result, album_dir=str(display_path(album_dir, cwd))
        )
        if troubleshoot:
            typer.echo("")
            typer.echo(troubleshoot, err=True)
        raise typer.Exit(code=1)


@album_app.command("check-all")
def check_all_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to recursively scan for iOS albums.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    album_dirs: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to check (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    checksum: Annotated[
        bool,
        typer.Option(
            "--checksum/--no-checksum",
            help="Enable/disable SHA-256 checksum verification (default: enabled).",
        ),
    ] = True,
    fatal_warnings: Annotated[
        bool,
        typer.Option(
            "--fatal-warnings",
            "-W",
            help="Treat informational warnings (e.g. missing sidecars) as errors.",
        ),
    ] = False,
    check_naming: Annotated[
        bool,
        typer.Option(
            "--check-naming/--no-check-naming",
            help="Enable/disable album naming convention checks (default: enabled).",
        ),
    ] = True,
    check_date_collisions: Annotated[
        bool,
        typer.Option(
            "--check-date-collisions/--no-check-date-collisions",
            help="Enable/disable cross-album date collision detection (default: enabled).",
        ),
    ] = True,
) -> None:
    """Check all albums under a directory or from an explicit list."""
    from .progress import BatchProgressBar

    cwd = Path.cwd()
    albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)

    # System checks (once)
    sips_available = album_preflight.check_sips_available()
    exiftool_available = check_exiftool_available()
    typer.echo("System Checks:")
    typer.echo(album_output.sips_check(sips_available))
    typer.echo(album_output.exiftool_check(exiftool_available))
    if not sips_available:
        typer.echo("")
        typer.echo(album_output.sips_troubleshoot(), err=True)
        raise typer.Exit(code=1)

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")
    else:
        typer.echo("")

    # Check each album
    progress = BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    )
    passed = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = _display_name(album_dir, display_base, cwd)

        progress.on_start(album_name)
        result = album_preflight.run_album_check(
            album_dir,
            sips_available=sips_available,
            exiftool_available=exiftool_available,
            checksum=checksum,
            check_naming_flag=check_naming,
        )

        album_ok = result.success and not (fatal_warnings and result.has_warnings)
        if album_ok:
            progress.on_end(album_name, success=True)
            passed += 1
        else:
            progress.on_end(album_name, success=False)
            failed_albums.append(album_dir)

    progress.stop()

    # Batch naming checks (date collisions across all albums)
    if check_naming and check_date_collisions:
        parsed_albums = [
            (album.name, parsed)
            for album in albums
            if (parsed := album_naming.parse_album_name(album.name)) is not None
        ]
        batch_naming = album_naming.check_batch_date_collisions(parsed_albums)
        typer.echo("")
        typer.echo(album_output.format_batch_naming_issues(batch_naming))
        if not batch_naming.success:
            failed_albums.append(albums[0])  # ensure non-zero exit

    # Summary
    typer.echo(album_output.batch_check_summary(passed, len(failed_albums)))

    if failed_albums:
        typer.echo("\nTo investigate failures:", err=True)
        for album_dir in sorted(set(failed_albums)):
            typer.echo(
                f'  photree album check --album-dir "{display_path(album_dir, cwd)}"',
                err=True,
            )
        raise typer.Exit(code=1)


@album_app.command("optimize")
def optimize_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to optimize.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = LinkMode.HARDLINK,
    check: Annotated[
        bool,
        typer.Option(
            "--check/--no-check",
            help="Run integrity checks before optimizing (default: enabled).",
        ),
    ] = True,
    checksum: Annotated[
        bool,
        typer.Option(
            "--checksum/--no-checksum",
            help="Enable/disable SHA-256 checksum verification (default: enabled).",
        ),
    ] = True,
) -> None:
    """Optimize main directories by replacing file copies with links.

    Recreates main-img/ and main-vid/ files as hard links (default),
    symbolic links, or copies depending on --link-mode. Does not touch
    main-jpg/ (those are HEIC-to-JPEG conversions that cannot be linked).

    Runs integrity checks first (unless --no-check) and refuses to optimize
    if errors are found.
    """
    if check:
        # Run checks first
        file_count = _count_unique_media_numbers(
            album_dir / ORIG_IMG_DIR, IMG_EXTENSIONS
        ) + _count_unique_media_numbers(album_dir / ORIG_VID_DIR, MOV_EXTENSIONS)
        progress = (
            SilentProgressBar(total=max(file_count, 1), description="Checking")
            if file_count > 0
            else None
        )

        check_result = album_preflight.run_album_preflight(
            album_dir,
            checksum=checksum,
            on_file_checked=progress.advance if progress else None,
        )
        if progress:
            progress.stop()

        typer.echo(album_output.format_album_preflight_checks(check_result))

        if not check_result.success:
            cwd = Path.cwd()
            troubleshoot = album_output.format_album_preflight_troubleshoot(
                check_result, album_dir=str(display_path(album_dir, cwd))
            )
            if troubleshoot:
                typer.echo("")
                typer.echo(troubleshoot, err=True)
            raise typer.Exit(code=1)

    # Optimize
    result = album_optimize.optimize_album(album_dir, link_mode=link_mode)
    typer.echo(
        album_output.optimize_summary(result.heic_count, result.mov_count, link_mode)
    )


@album_app.command("optimize-all")
def optimize_all_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to recursively scan for iOS albums.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    album_dirs: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to optimize (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = LinkMode.HARDLINK,
    check: Annotated[
        bool,
        typer.Option(
            "--check/--no-check",
            help="Run integrity checks before optimizing (default: enabled).",
        ),
    ] = True,
    checksum: Annotated[
        bool,
        typer.Option(
            "--checksum/--no-checksum",
            help="Enable/disable SHA-256 checksum verification (default: enabled).",
        ),
    ] = True,
) -> None:
    """Optimize all iOS albums under a directory or from an explicit list.

    Runs integrity checks on each album first (unless --no-check), then
    replaces main-img/ and main-vid/ file copies with links.
    """
    from .progress import BatchProgressBar

    cwd = Path.cwd()
    albums, display_base = _resolve_batch_albums(base_dir, album_dirs)

    sips_available = True
    if check:
        # System checks (once)
        sips_available = album_preflight.check_sips_available()
        typer.echo("System Checks:")
        typer.echo(album_output.sips_check(sips_available))
        if not sips_available:
            typer.echo("")
            typer.echo(album_output.sips_troubleshoot(), err=True)
            raise typer.Exit(code=1)

    if not albums:
        typer.echo("\nNo iOS albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} iOS album(s).\n")
    else:
        typer.echo("")

    # Check and optimize each album
    progress = BatchProgressBar(
        total=len(albums), description="Optimizing", done_description="optimize"
    )
    optimized = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = _display_name(album_dir, display_base, cwd)

        progress.on_start(album_name)

        if check:
            check_result = album_preflight.run_album_check(
                album_dir,
                sips_available=sips_available,
                exiftool_available=False,
                checksum=checksum,
                check_naming_flag=False,
            )
            if not check_result.success:
                progress.on_end(album_name, success=False)
                failed_albums.append(album_dir)
                continue

        album_optimize.optimize_album(album_dir, link_mode=link_mode)
        progress.on_end(album_name, success=True)
        optimized += 1

    progress.stop()

    # Summary
    typer.echo(album_output.batch_optimize_summary(optimized, len(failed_albums)))

    if failed_albums:
        typer.echo("\nTo investigate failures:", err=True)
        for album_dir in failed_albums:
            typer.echo(
                f'  photree album check --album-dir "{display_path(album_dir, cwd)}"',
                err=True,
            )
        raise typer.Exit(code=1)


def _resolve_check_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], Path | None]:
    """Resolve album list for check commands (all album types).

    Uses :func:`discover_albums` which detects iOS albums, ``.album``
    sentinels, and leaf directories.
    """
    return _resolve_batch_albums_with(
        base_dir, album_dirs, album_preflight.discover_albums
    )


def _resolve_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], Path | None]:
    """Resolve album list for iOS-specific commands.

    Uses :func:`discover_ios_albums` which only finds albums with an
    ``ios/`` subdirectory.
    """
    return _resolve_batch_albums_with(
        base_dir, album_dirs, album_preflight.discover_ios_albums
    )


def _resolve_batch_albums_with(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    discover_fn: Callable[[Path], list[Path]],
) -> tuple[list[Path], Path | None]:
    """Resolve album list from mutually exclusive --dir / --album-dir options.

    Returns ``(albums, display_base)`` where *display_base* is the base
    directory when --dir was used (for relative display names), or ``None``
    when --album-dir was used (display names are CWD-relative).
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn

    if base_dir is not None and album_dirs is not None:
        typer.echo(
            "--dir and --album-dir are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=1)

    if album_dirs is not None:
        return (album_dirs, None)

    # --dir mode (explicit or default)
    resolved_base = base_dir if base_dir is not None else Path(".").resolve()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Resolving album list...", total=None)
        albums = discover_fn(resolved_base)
    return (albums, resolved_base)


def _display_name(album_dir: Path, base_dir: Path | None, cwd: Path) -> str:
    """Human-readable album name relative to *base_dir* or *cwd*."""
    if base_dir is not None:
        return str(album_dir.relative_to(base_dir))

    return str(display_path(album_dir, cwd))


@album_app.command("fix-ios")
def fix_ios_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="iOS album directory to fix.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = LinkMode.HARDLINK,
    refresh_combined: Annotated[
        bool,
        typer.Option(
            "--refresh-combined",
            help="Rebuild main-img/ and main-vid/ from orig/edit, then regenerate main-jpg/.",
        ),
    ] = False,
    refresh_jpeg: Annotated[
        bool,
        typer.Option(
            "--refresh-jpeg",
            help="Refresh main-jpg/ from main-img/ (re-convert all HEIC→JPEG).",
        ),
    ] = False,
    rm_upstream: Annotated[
        bool,
        typer.Option(
            "--rm-upstream",
            help="Propagate deletions from browsing dirs (main-jpg, main-vid) to upstream dirs.",
        ),
    ] = False,
    rm_orphan: Annotated[
        bool,
        typer.Option(
            "--rm-orphan",
            help="Delete edited and main files that have no corresponding orig file.",
        ),
    ] = False,
    prefer_higher_quality_when_dups: Annotated[
        bool,
        typer.Option(
            "--prefer-higher-quality-when-dups",
            help="Delete lower-quality duplicates (e.g. JPG when DNG or HEIC exists for the same number).",
        ),
    ] = False,
    rm_orphan_sidecar: Annotated[
        bool,
        typer.Option(
            "--rm-orphan-sidecar",
            help="Delete AAE sidecar files that have no matching media file.",
        ),
    ] = False,
    rm_miscategorized: Annotated[
        bool,
        typer.Option(
            "--rm-miscategorized",
            help="Delete files in the wrong directory (edited in orig or vice versa).",
        ),
    ] = False,
    rm_miscategorized_safe: Annotated[
        bool,
        typer.Option(
            "--rm-miscategorized-safe",
            help="Delete miscategorized files only if they already exist in the correct directory.",
        ),
    ] = False,
    mv_miscategorized: Annotated[
        bool,
        typer.Option(
            "--mv-miscategorized",
            help="Move files in the wrong directory to the correct one.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Fix iOS album issues. At least one fix flag must be specified.

    Available fixes:

    --refresh-combined: Deletes main-img/, main-vid/, and
    main-jpg/, then rebuilds main-img and main-vid from
    orig/edit sources. If main-img/ is created, also regenerates
    main-jpg/ via HEIC→JPEG conversion.

    --refresh-jpeg: Deletes all files in main-jpg/ and re-converts
    every file from main-img/. HEIC files are converted via sips;
    JPEG/PNG files are copied as-is.

    --rm-upstream: Propagates deletions from browsing directories to
    upstream directories. Files deleted from main-jpg/ are removed
    from main-img/, edit-img/, and orig-img/. Files deleted
    from main-vid/ are removed from edit-vid/ and orig-vid/.

    --rm-orphan: Deletes edited and main files whose image number
    has no corresponding original file in orig-img/ or orig-vid/.

    --rm-orphan-sidecar: Deletes AAE sidecar files in orig-img/,
    edit-img/, orig-vid/, and edit-vid/ that have no matching
    media file.

    --prefer-higher-quality-when-dups: When multiple format variants exist for the
    same image number (e.g. DNG + HEIC, or HEIC + JPG), deletes the lower-quality
    file from all image subdirectories. Priority: DNG > HEIC > JPG/PNG.

    --rm-miscategorized: Deletes files that are in the wrong directory
    (e.g. edited files in orig-img/ or original files in edit-img/).

    --rm-miscategorized-safe: Like --rm-miscategorized, but only deletes
    a miscategorized file if it already exists in the correct directory.
    Safe to run when you're unsure whether the file was copied or moved.

    --mv-miscategorized: Moves files to the correct directory instead of
    deleting them (e.g. edited files from orig-img/ to edit-img/).
    """
    cwd = Path.cwd()

    album_type = album_preflight.detect_album_type(album_dir)
    if album_type != album_preflight.AlbumType.IOS:
        typer.echo(
            f"Album type is '{album_type.value}', but fix-ios only supports iOS albums.",
            err=True,
        )
        raise typer.Exit(code=1)

    _validate_fix_flags(
        refresh_combined=refresh_combined,
        refresh_jpeg=refresh_jpeg,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
    )

    _run_fix_ios(
        album_dir,
        link_mode=link_mode,
        dry_run=dry_run,
        log_cwd=cwd,
        show_progress=True,
        refresh_combined=refresh_combined,
        refresh_jpeg=refresh_jpeg,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
    )


@album_app.command("fix-ios-all")
def fix_ios_all_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to recursively scan for iOS albums.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    album_dirs: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--album-dir",
            "-a",
            help="iOS album directory to fix (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = LinkMode.HARDLINK,
    refresh_combined: Annotated[
        bool,
        typer.Option(
            "--refresh-combined",
            help="Rebuild main-img/ and main-vid/ from orig/edit, then regenerate main-jpg/.",
        ),
    ] = False,
    refresh_jpeg: Annotated[
        bool,
        typer.Option(
            "--refresh-jpeg",
            help="Refresh main-jpg/ from main-img/ (re-convert all HEIC→JPEG).",
        ),
    ] = False,
    rm_upstream: Annotated[
        bool,
        typer.Option(
            "--rm-upstream",
            help="Propagate deletions from browsing dirs (main-jpg, main-vid) to upstream dirs.",
        ),
    ] = False,
    rm_orphan: Annotated[
        bool,
        typer.Option(
            "--rm-orphan",
            help="Delete edited and main files that have no corresponding orig file.",
        ),
    ] = False,
    prefer_higher_quality_when_dups: Annotated[
        bool,
        typer.Option(
            "--prefer-higher-quality-when-dups",
            help="Delete lower-quality duplicates (e.g. JPG when DNG or HEIC exists for the same number).",
        ),
    ] = False,
    rm_orphan_sidecar: Annotated[
        bool,
        typer.Option(
            "--rm-orphan-sidecar",
            help="Delete AAE sidecar files that have no matching media file.",
        ),
    ] = False,
    rm_miscategorized: Annotated[
        bool,
        typer.Option(
            "--rm-miscategorized",
            help="Delete files in the wrong directory (edited in orig or vice versa).",
        ),
    ] = False,
    rm_miscategorized_safe: Annotated[
        bool,
        typer.Option(
            "--rm-miscategorized-safe",
            help="Delete miscategorized files only if they already exist in the correct directory.",
        ),
    ] = False,
    mv_miscategorized: Annotated[
        bool,
        typer.Option(
            "--mv-miscategorized",
            help="Move files in the wrong directory to the correct one.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Apply fix-ios to all iOS albums under a directory or from an explicit list.

    Accepts the same fix flags as fix-ios. At least one fix flag must be specified.
    """
    from .progress import BatchProgressBar

    cwd = Path.cwd()

    _validate_fix_flags(
        refresh_combined=refresh_combined,
        refresh_jpeg=refresh_jpeg,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
    )

    albums, display_base = _resolve_batch_albums(base_dir, album_dirs)

    if not albums:
        typer.echo("No iOS albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"Found {len(albums)} iOS album(s).\n")

    import io
    from contextlib import redirect_stdout

    progress = BatchProgressBar(
        total=len(albums), description="Fixing", done_description="fix-ios"
    )
    fixed = 0
    failed_albums: list[Path] = []
    album_reports: list[tuple[str, str]] = []

    for album_dir in albums:
        album_name = _display_name(album_dir, display_base, cwd)
        progress.on_start(album_name)

        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                _run_fix_ios(
                    album_dir,
                    link_mode=link_mode,
                    dry_run=dry_run,
                    log_cwd=cwd,
                    show_progress=False,
                    refresh_combined=refresh_combined,
                    refresh_jpeg=refresh_jpeg,
                    rm_upstream=rm_upstream,
                    rm_orphan=rm_orphan,
                    rm_orphan_sidecar=rm_orphan_sidecar,
                    prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
                    rm_miscategorized=rm_miscategorized,
                    rm_miscategorized_safe=rm_miscategorized_safe,
                    mv_miscategorized=mv_miscategorized,
                )
            progress.on_end(album_name, success=True)
            fixed += 1
            captured = buf.getvalue()
            if captured.strip():
                album_reports.append((album_name, captured))
        except Exception:
            progress.on_end(album_name, success=False)
            failed_albums.append(album_dir)

    progress.stop()

    # Print per-album action reports (e.g. dry-run details).
    # Use color=True to preserve ANSI escapes captured from the fix run.
    if album_reports:
        typer.echo("")
        for album_name, report in album_reports:
            typer.echo(f"{album_name}:")
            typer.echo(report, color=True)

    typer.echo(album_output.batch_fix_ios_summary(fixed, len(failed_albums)))

    if failed_albums:
        typer.echo("\nFailed albums:", err=True)
        for album_dir in failed_albums:
            typer.echo(
                f'  photree album fix-ios --album-dir "{display_path(album_dir, cwd)}"',
                err=True,
            )
        raise typer.Exit(code=1)


def _validate_fix_flags(
    *,
    refresh_combined: bool,
    refresh_jpeg: bool,
    rm_upstream: bool,
    rm_orphan: bool,
    rm_orphan_sidecar: bool,
    prefer_higher_quality_when_dups: bool,
    rm_miscategorized: bool,
    rm_miscategorized_safe: bool,
    mv_miscategorized: bool,
) -> None:
    """Validate fix flag combinations. Exits on error."""
    miscat_flags = sum([rm_miscategorized, rm_miscategorized_safe, mv_miscategorized])
    if miscat_flags > 1:
        typer.echo(
            "--rm-miscategorized, --rm-miscategorized-safe, and --mv-miscategorized "
            "are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=1)

    any_fix = (
        refresh_combined
        or refresh_jpeg
        or rm_upstream
        or rm_orphan
        or rm_orphan_sidecar
        or prefer_higher_quality_when_dups
        or miscat_flags > 0
    )
    if not any_fix:
        typer.echo(
            "No fix specified. Run photree album fix-ios --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)


def _run_fix_ios(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    log_cwd: Path | None = None,
    show_progress: bool = True,
    refresh_combined: bool,
    refresh_jpeg: bool,
    rm_upstream: bool,
    rm_orphan: bool,
    rm_orphan_sidecar: bool,
    prefer_higher_quality_when_dups: bool,
    rm_miscategorized: bool,
    rm_miscategorized_safe: bool,
    mv_miscategorized: bool,
) -> None:
    """Run the selected fix-ios operations on a single album.

    *log_cwd* enables per-file action lines (``✓ delete ...``).
    *show_progress* enables progress bars and summary lines.
    Both can be set independently.
    """

    if refresh_combined:
        _check_sips_or_exit()
        stage_progress = (
            StageProgressBar(
                total=4,
                labels={
                    "delete": "Deleting main directories",
                    "refresh-heic": "Rebuilding main-img",
                    "refresh-mov": "Rebuilding main-vid",
                    "refresh-jpeg": "Converting HEIC to JPEG",
                },
            )
            if show_progress
            else None
        )
        result = ios_fixes.refresh_combined(
            album_dir,
            link_mode=link_mode,
            dry_run=dry_run,
            on_stage_start=stage_progress.on_start if stage_progress else None,
            on_stage_end=stage_progress.on_end if stage_progress else None,
        )
        if stage_progress:
            stage_progress.stop()
        if show_progress:
            typer.echo(
                album_output.refresh_combined_summary(
                    heic_copied=result.heic.copied,
                    mov_copied=result.mov.copied,
                    jpeg_converted=result.jpeg.converted if result.jpeg else 0,
                    jpeg_copied=result.jpeg.copied if result.jpeg else 0,
                    jpeg_skipped=result.jpeg.skipped if result.jpeg else 0,
                )
            )
    elif refresh_jpeg:
        _check_sips_or_exit()
        src_dir = album_dir / MAIN_IMG_DIR
        if not src_dir.is_dir():
            typer.echo(f"Directory not found: {src_dir}", err=True)
            raise typer.Exit(code=1)
        file_count = len(list_files(src_dir))
        progress = (
            FileProgressBar(
                total=file_count,
                description="Converting JPEG",
                done_description="convert-jpeg",
            )
            if show_progress
            else None
        )
        result_jpeg = ios_fixes.refresh_jpeg(
            album_dir,
            dry_run=dry_run,
            log_cwd=log_cwd,
            on_file_start=progress.on_start if progress else None,
            on_file_end=progress.on_end if progress else None,
        )
        if progress:
            progress.stop()
        if show_progress:
            typer.echo(
                album_output.refresh_jpeg_summary(
                    result_jpeg.converted, result_jpeg.copied, result_jpeg.skipped
                )
            )

    if rm_upstream:
        result_rm = ios_fixes.rm_upstream(album_dir, dry_run=dry_run, log_cwd=log_cwd)
        if show_progress:
            typer.echo(
                album_output.rm_upstream_summary(
                    heic_jpeg=len(result_rm.heic.removed_jpeg),
                    heic_combined=len(result_rm.heic.removed_combined),
                    heic_rendered=len(result_rm.heic.removed_rendered),
                    heic_orig=len(result_rm.heic.removed_orig),
                    mov_rendered=len(result_rm.mov.removed_rendered),
                    mov_orig=len(result_rm.mov.removed_orig),
                )
            )

    if rm_orphan:
        result_orphan = ios_fixes.rm_orphan(album_dir, dry_run=dry_run, log_cwd=log_cwd)
        if show_progress:
            typer.echo(
                album_output.rm_orphan_summary(
                    (
                        *result_orphan.heic.removed_by_dir,
                        *result_orphan.mov.removed_by_dir,
                    )
                )
            )

    if rm_orphan_sidecar:
        result_meta = ios_fixes.rm_orphan_sidecar(
            album_dir, dry_run=dry_run, log_cwd=log_cwd
        )
        if show_progress:
            typer.echo(
                album_output.rm_orphan_sidecar_summary(result_meta.removed_by_dir)
            )

    if prefer_higher_quality_when_dups:
        result_heic = ios_fixes.prefer_higher_quality_when_dups(
            album_dir, dry_run=dry_run, log_cwd=log_cwd
        )
        if show_progress:
            typer.echo(
                album_output.prefer_higher_quality_summary(result_heic.removed_by_dir)
            )

    miscat_action = (
        "rm"
        if rm_miscategorized
        else "rm-safe"
        if rm_miscategorized_safe
        else "mv"
        if mv_miscategorized
        else None
    )
    if miscat_action:
        fix_fn = {
            "rm": ios_fixes.rm_miscategorized,
            "rm-safe": ios_fixes.rm_miscategorized_safe,
            "mv": ios_fixes.mv_miscategorized,
        }[miscat_action]
        result_miscat = fix_fn(album_dir, dry_run=dry_run, log_cwd=log_cwd)
        if show_progress:
            typer.echo(
                album_output.miscategorized_summary(
                    action=miscat_action,
                    heic_from_orig=len(result_miscat.heic.fixed_from_orig),
                    heic_from_rendered=len(result_miscat.heic.fixed_from_rendered),
                    mov_from_orig=len(result_miscat.mov.fixed_from_orig),
                    mov_from_rendered=len(result_miscat.mov.fixed_from_rendered),
                )
            )


def _check_sips_or_exit() -> None:
    if not album_preflight.check_sips_available():
        typer.echo(album_output.sips_check(False), err=True)
        typer.echo(album_output.sips_troubleshoot(), err=True)
        raise typer.Exit(code=1)


def _count_unique_media_numbers(directory: Path, extensions: frozenset[str]) -> int:
    """Count unique image numbers among media files in a directory."""
    return len(
        {
            "".join(c for c in f if c.isdigit())
            for f in list_files(directory)
            if Path(f).suffix.lower() in extensions
        }
    )
