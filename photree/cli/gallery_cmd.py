"""CLI commands for the ``photree gallery`` sub-app.

Gallery commands operate on multiple albums at once (batch operations).
"""

from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import Annotated, Optional

import typer

from ..album import (
    fixes as album_fixes,
    naming as album_naming,
    optimize as album_optimize,
    output as album_output,
    preflight as album_preflight,
)
from ..album.exif import try_start_exiftool
from ..fsprotocol import (
    LinkMode,
    discover_contributors,
    display_path,
)
from .album_cmd import (
    _check_sips_or_exit,
    _run_fix_ios,
    _validate_fix_flags,
)
from .console import console, err_console
from .progress import BatchProgressBar

gallery_app = typer.Typer(
    name="gallery",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)


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


@gallery_app.command("list-albums")
def list_albums_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to recursively scan for albums.",
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
            help="Album directory (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    metadata: Annotated[
        bool,
        typer.Option(
            "--metadata/--no-metadata",
            help="Show parsed album metadata and contributors (default: enabled).",
        ),
    ] = True,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: text (default) or csv.",
        ),
    ] = "text",
) -> None:
    """List all discovered albums with their metadata and contributors."""
    import csv
    import sys

    from ..album.naming import parse_album_name

    if output_format == "csv":
        # Resolve without spinner to avoid polluting stdout
        from ..fsprotocol import discover_albums as _discover

        if base_dir is not None and album_dirs is not None:
            typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
            raise typer.Exit(code=1)
        if album_dirs is not None:
            albums, display_base = album_dirs, None
        else:
            resolved = base_dir if base_dir is not None else Path(".").resolve()
            albums, display_base = _discover(resolved), resolved
    else:
        albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)

    cwd = Path.cwd()

    if not albums:
        typer.echo("No albums found.", err=output_format == "csv")
        raise typer.Exit(code=0)

    if output_format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(
            [
                "path",
                "date",
                "part",
                "series",
                "title",
                "location",
                "tags",
                "contributors",
            ]
        )
        for album_dir in albums:
            rel_path = _display_name(album_dir, display_base, cwd)
            parsed = parse_album_name(album_dir.name)
            contribs = discover_contributors(album_dir)
            contrib_desc = ", ".join(
                f"{c.name} ({c.contributor_type})" for c in contribs
            )
            if parsed is not None:
                tags = "private" if parsed.private else ""
                writer.writerow(
                    [
                        rel_path,
                        parsed.date,
                        parsed.part or "",
                        parsed.series or "",
                        parsed.title,
                        parsed.location or "",
                        tags,
                        contrib_desc,
                    ]
                )
            else:
                writer.writerow(
                    [rel_path, "", "", "", album_dir.name, "", "", contrib_desc]
                )
        return

    typer.echo(f"Found {len(albums)} album(s).\n")

    for album_dir in albums:
        name = _display_name(album_dir, display_base, cwd)
        typer.echo(name)

        if metadata:
            parsed = parse_album_name(album_dir.name)
            contribs = discover_contributors(album_dir)

            if parsed is not None:
                parts = [f"date={parsed.date}"]
                if parsed.part is not None:
                    parts.append(f"part={parsed.part}")
                if parsed.series is not None:
                    parts.append(f"series={parsed.series}")
                parts.append(f"title={parsed.title}")
                if parsed.location is not None:
                    parts.append(f"location={parsed.location}")
                if parsed.private:
                    parts.append("private")
                typer.echo(f"  {', '.join(parts)}")
            else:
                typer.echo("  (name not parseable)")

            if contribs:
                contrib_desc = ", ".join(
                    f"{c.name} ({c.contributor_type})" for c in contribs
                )
                typer.echo(f"  contributors: {contrib_desc}")


@gallery_app.command("check")
def check_cmd(
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
            help="Treat all warnings as errors (implies --fatal-sidecar and --fatal-exif-date-match).",
        ),
    ] = False,
    fatal_sidecar_arg: Annotated[
        bool,
        typer.Option(
            "--fatal-sidecar",
            help="Treat missing-sidecar warnings as errors.",
        ),
    ] = False,
    fatal_exif_date_match: Annotated[
        bool,
        typer.Option(
            "--fatal-exif-date-match",
            help="Treat EXIF date mismatch warnings as errors.",
        ),
    ] = False,
    check_naming: Annotated[
        bool,
        typer.Option(
            "--check-naming/--no-check-naming",
            help="Enable/disable album naming convention checks (default: enabled).",
        ),
    ] = True,
    check_date_part_collision: Annotated[
        bool,
        typer.Option(
            "--check-date-part-collision/--no-check-date-part-collision",
            help="Enable/disable cross-album date collision detection (default: enabled).",
        ),
    ] = True,
    check_exif_date_match: Annotated[
        bool,
        typer.Option(
            "--check-exif-date-match/--no-check-exif-date-match",
            help="Enable/disable EXIF timestamp vs album date validation (default: enabled).",
        ),
    ] = True,
) -> None:
    """Check all albums under a directory or from an explicit list."""

    cwd = Path.cwd()
    albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)

    # System checks (once)
    sips_available = album_preflight.check_sips_available()
    exiftool = try_start_exiftool() if check_exif_date_match else None
    exiftool_available = exiftool is not None
    typer.echo("System Checks:")
    console.print(album_output.sips_check(sips_available))
    console.print(album_output.exiftool_check(exiftool_available))
    if not sips_available:
        typer.echo("")
        err_console.print(album_output.sips_troubleshoot())
        raise typer.Exit(code=1)

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")
    else:
        typer.echo("")

    # Check each album
    fatal_sidecar = fatal_warnings or fatal_sidecar_arg
    fatal_exif = fatal_warnings or fatal_exif_date_match

    progress = BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    )
    passed = 0
    warned = 0
    failed_albums: list[Path] = []

    try:
        for album_dir in albums:
            album_name = _display_name(album_dir, display_base, cwd)

            progress.on_start(album_name)
            result = album_preflight.run_album_check(
                album_dir,
                sips_available=sips_available,
                exiftool=exiftool,
                checksum=checksum,
                check_naming_flag=check_naming,
            )

            album_ok = result.success and not result.has_fatal_warnings(
                fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
            )
            # Error labels = real errors + fatal-promoted warnings (red)
            # Warning labels = non-fatal warnings only (orange)
            err_labels = (
                *result.error_labels,
                *result.fatal_warning_labels(
                    fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
                ),
            )
            warn_labels = result.non_fatal_warning_labels(
                fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
            )
            if album_ok:
                progress.on_end(
                    album_name,
                    success=True,
                    warning_labels=warn_labels,
                )
                passed += 1
                if result.has_warnings:
                    warned += 1
            else:
                progress.on_end(
                    album_name,
                    success=False,
                    error_labels=err_labels,
                    warning_labels=warn_labels,
                )
                failed_albums.append(album_dir)
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)

    progress.stop()

    # Batch naming checks (date collisions across all albums)
    if check_naming and check_date_part_collision:
        parsed_albums = [
            (album.name, parsed)
            for album in albums
            if (parsed := album_naming.parse_album_name(album.name)) is not None
        ]
        batch_naming = album_naming.check_batch_date_collisions(parsed_albums)
        typer.echo("")
        console.print(album_output.format_batch_naming_issues(batch_naming))
        if not batch_naming.success:
            colliding_names = {
                name for _, names in batch_naming.date_collisions for name in names
            }
            failed_albums.extend(a for a in albums if a.name in colliding_names)

    # Summary
    console.print(album_output.batch_check_summary(passed, len(failed_albums), warned))

    if failed_albums:
        extra_flags = "".join(
            [
                " --fatal-warnings" if fatal_warnings else "",
                " --fatal-sidecar" if fatal_sidecar_arg else "",
                " --fatal-exif-date-match" if fatal_exif_date_match else "",
            ]
        )
        err_console.print("\nTo investigate failures:")
        for album_dir in sorted(set(failed_albums)):
            err_console.print(
                f'  photree album check --album-dir "{display_path(album_dir, cwd)}"{extra_flags}'
            )
        raise typer.Exit(code=1)


@gallery_app.command("fix")
def fix_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to recursively scan for albums.",
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
            help="Album directory to fix (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    refresh_jpeg: Annotated[
        bool,
        typer.Option(
            "--refresh-jpeg",
            help="Refresh {contributor}-jpg/ from {contributor}-img/ for all contributors.",
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
    """Fix all albums under a directory or from an explicit list.

    Works on all contributor types (iOS + plain). At least one fix flag
    must be specified.
    """

    if not refresh_jpeg:
        typer.echo(
            "No fix specified. Run photree album fix-all --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)

    if refresh_jpeg:
        _check_sips_or_exit()

    cwd = Path.cwd()
    albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")

    progress = BatchProgressBar(
        total=len(albums), description="Fixing", done_description="fix"
    )
    fixed = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = _display_name(album_dir, display_base, cwd)
        progress.on_start(album_name)

        try:
            contributors = discover_contributors(album_dir)
            if refresh_jpeg:
                for contrib in contributors:
                    if (album_dir / contrib.img_dir).is_dir():
                        album_fixes.refresh_jpeg(album_dir, contrib, dry_run=dry_run)
            progress.on_end(album_name, success=True)
            fixed += 1
        except Exception:
            progress.on_end(album_name, success=False)
            failed_albums.append(album_dir)

    progress.stop()

    typer.echo(f"\nDone. {fixed} album(s) fixed, {len(failed_albums)} failed.")

    if failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in failed_albums:
            err_console.print(
                f'  photree album fix --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)


@gallery_app.command("optimize")
def optimize_cmd(
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
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Optimize all iOS albums under a directory or from an explicit list.

    Runs structural integrity checks on each album first (unless --no-check):
    directory structure, file matching, checksums, sidecars, duplicates, and
    miscategorized files. Naming and EXIF checks are not performed.

    Albums that pass are optimized by replacing main-img/ and main-vid/
    file copies with links.
    """

    cwd = Path.cwd()
    albums, display_base = _resolve_batch_albums(base_dir, album_dirs)

    sips_available = True
    if check:
        # System checks (once)
        sips_available = album_preflight.check_sips_available()
        typer.echo("System Checks:")
        console.print(album_output.sips_check(sips_available))
        if not sips_available:
            typer.echo("")
            err_console.print(album_output.sips_troubleshoot())
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
                exiftool=None,
                checksum=checksum,
                check_naming_flag=False,
            )
            if not check_result.success:
                progress.on_end(album_name, success=False)
                failed_albums.append(album_dir)
                continue

        album_optimize.optimize_album(album_dir, link_mode=link_mode, dry_run=dry_run)
        progress.on_end(album_name, success=True)
        optimized += 1

    progress.stop()

    # Summary
    console.print(album_output.batch_optimize_summary(optimized, len(failed_albums)))

    if failed_albums:
        err_console.print("\nTo investigate failures:")
        for album_dir in failed_albums:
            err_console.print(
                f'  photree album check --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)


@gallery_app.command("fix-ios")
def fix_ios_cmd(
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

    console.print(album_output.batch_fix_ios_summary(fixed, len(failed_albums)))

    if failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in failed_albums:
            err_console.print(
                f'  photree album fix-ios --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)


@gallery_app.command("rename-from-csv")
def rename_from_csv_cmd(
    current_csv: Annotated[
        Path,
        typer.Argument(
            help="CSV with current album state (from gallery list-albums --format csv).",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    desired_csv: Annotated[
        Path,
        typer.Argument(
            help="CSV with desired album state (edited copy of current).",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    base_dir: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Root directory (base for relative paths in CSV).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show what would be renamed without making changes.",
        ),
    ] = False,
) -> None:
    """Rename albums by diffing current vs desired CSV files (from list-albums --format csv).

    Only the series, title, and location columns may differ between the two files.
    """
    import csv
    import unicodedata

    from ..album.naming import ParsedAlbumName, reconstruct_name

    def _nfc(s: str) -> str:
        return unicodedata.normalize("NFC", s)

    def _name_from_row(row: dict[str, str]) -> str:
        parsed = ParsedAlbumName(
            date=row["date"],
            part=row["part"] or None,
            private="private" in row.get("tags", ""),
            series=row["series"] or None,
            title=row["title"],
            location=row["location"] or None,
        )
        return reconstruct_name(parsed)

    with open(current_csv, encoding="utf-8") as f:
        current_rows = {r["path"]: r for r in csv.DictReader(f)}

    with open(desired_csv, encoding="utf-8") as f:
        desired_rows = {r["path"]: r for r in csv.DictReader(f)}

    if not desired_rows:
        typer.echo("Desired CSV is empty.")
        raise typer.Exit(code=0)

    # Fields that must not differ between current and desired
    immutable_fields = ("path", "date", "part", "tags", "contributors")

    renames: list[tuple[Path, str]] = []
    errors: list[str] = []

    for path, desired in desired_rows.items():
        current = current_rows.get(path)
        if current is None:
            errors.append(f"Path not found in current CSV: {path}")
            continue

        # Safety: only title and location may be changed
        for field in immutable_fields:
            if _nfc(current.get(field, "")) != _nfc(desired.get(field, "")):
                errors.append(
                    f"{path}: field '{field}' was modified "
                    f"({current.get(field, '')!r} → {desired.get(field, '')!r}). "
                    f"Only 'series', 'title', and 'location' may be changed."
                )

        # Only process rows where series, title, or location actually changed
        series_changed = _nfc(current.get("series", "")) != _nfc(
            desired.get("series", "")
        )
        title_changed = _nfc(current.get("title", "")) != _nfc(desired.get("title", ""))
        location_changed = _nfc(current.get("location", "")) != _nfc(
            desired.get("location", "")
        )
        if not series_changed and not title_changed and not location_changed:
            continue

        album_path = base_dir / path
        if not album_path.is_dir():
            errors.append(f"Directory not found: {path}")
            continue

        desired_name = _name_from_row(desired)
        renames.append((album_path, desired_name))

    if errors:
        for err in errors:
            typer.echo(f"  {err}", err=True)
        raise typer.Exit(code=1)

    if not renames:
        typer.echo(
            f"Current: {len(current_rows)} rows, "
            f"desired: {len(desired_rows)} rows. Nothing to rename."
        )
        raise typer.Exit(code=0)

    # Check for collisions (resolve() handles case-insensitive macOS)
    renamed_resolved = {album_path.resolve() for album_path, _ in renames}
    for album_path, desired_name in renames:
        target = album_path.parent / desired_name
        if (
            target.exists()
            and target.resolve() != album_path.resolve()
            and target.resolve() not in renamed_resolved
        ):
            typer.echo(
                f"Collision: {album_path.relative_to(base_dir)} → {desired_name} "
                f"conflicts with {target.relative_to(base_dir)}",
                err=True,
            )
            raise typer.Exit(code=1)

    # Display plan
    typer.echo(
        f"Current: {len(current_rows)} rows, desired: {len(desired_rows)} rows, "
        f"changes: {len(renames)}"
    )
    typer.echo()

    for album_path, desired_name in renames:
        typer.echo(f"  {album_path.relative_to(base_dir)}")
        typer.echo(f"  → {desired_name}")
        typer.echo()

    if dry_run:
        typer.echo(f"[dry run] {len(renames)} album(s) would be renamed.")
    else:
        for album_path, desired_name in renames:
            new_path = album_path.parent / desired_name
            album_path.rename(new_path)

        typer.echo(f"Renamed {len(renames)} album(s).")


# Re-register the export batch command from export_cmd
from .export_cmd import export_all_cmd  # noqa: E402

gallery_app.command("export")(export_all_cmd)
