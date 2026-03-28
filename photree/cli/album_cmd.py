"""CLI commands for the ``photree album`` sub-app."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..album import (
    exif as album_exif,
    fixes as album_fixes,
    ios_fixes,
    media_ops,
    naming as album_naming,
    optimize as album_optimize,
    output as album_output,
    preflight as album_preflight,
    stats as album_stats,
)
from ..fsprotocol import (
    IMG_EXTENSIONS,
    LinkMode,
    VID_EXTENSIONS,
    discover_albums,
    discover_media_sources,
    display_path,
    list_files,
)
from .console import console, err_console
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
            help="Treat all warnings as errors (implies --fatal-sidecar).",
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
            "--fatal-exif-date-match/--no-fatal-exif-date-match",
            help="Treat EXIF date mismatch warnings as errors (default: enabled).",
        ),
    ] = True,
    check_naming: Annotated[
        bool,
        typer.Option(
            "--check-naming/--no-check-naming",
            help="Enable/disable album naming convention checks (default: enabled).",
        ),
    ] = True,
    check_exif_date_match: Annotated[
        bool,
        typer.Option(
            "--check-exif-date-match/--no-check-exif-date-match",
            help="Enable/disable EXIF timestamp vs album date validation (default: enabled).",
        ),
    ] = True,
    check_date_part_collision: Annotated[
        bool,
        typer.Option(
            "--check-date-part-collision/--no-check-date-part-collision",
            help="Enable/disable date collision detection with sibling albums (default: enabled).",
        ),
    ] = True,
) -> None:
    """Check system prerequisites, album directory structure, and file integrity."""
    # Count unique media numbers across all media_sources' orig dirs
    file_count = sum(
        _count_unique_media_numbers(album_dir / c.orig_img_dir, IMG_EXTENSIONS)
        + _count_unique_media_numbers(album_dir / c.orig_vid_dir, VID_EXTENSIONS)
        for c in discover_media_sources(album_dir)
    )
    progress = (
        SilentProgressBar(total=max(file_count, 1), description="Checking")
        if file_count > 0
        else None
    )

    result = album_preflight.run_album_preflight(
        album_dir,
        checksum=checksum,
        check_naming_flag=check_naming,
        check_exif_date_match=check_exif_date_match,
        on_file_checked=progress.advance if progress else None,
    )
    if progress:
        progress.stop()

    fatal_sidecar = fatal_warnings or fatal_sidecar_arg
    fatal_exif = fatal_warnings or fatal_exif_date_match

    cwd = Path.cwd()
    album_dir_display = str(display_path(album_dir, cwd))

    console.print(
        album_output.format_album_preflight_checks(
            result,
            fatal_sidecar=fatal_sidecar,
            fatal_exif=fatal_exif,
            album_dir=album_dir_display,
        )
    )
    failed = not result.success or result.has_fatal_warnings(
        fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
    )

    # Date collision detection against sibling albums
    if check_naming and check_date_part_collision:
        siblings = discover_albums(album_dir.parent)
        parsed_siblings = [
            (a.name, parsed)
            for a in siblings
            if (parsed := album_naming.parse_album_name(a.name)) is not None
        ]
        batch_naming = album_naming.check_batch_date_collisions(parsed_siblings)
        console.print(album_output.format_batch_naming_issues(batch_naming))
        if not batch_naming.success:
            failed = True

    if failed:
        troubleshoot = album_output.format_album_preflight_troubleshoot(
            result, album_dir=album_dir_display
        )
        if troubleshoot:
            typer.echo("")
            err_console.print(troubleshoot)
        if result.success and result.has_fatal_warnings(
            fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
        ):
            typer.echo("")
            err_console.print(
                album_output.format_fatal_warnings(
                    result,
                    fatal_sidecar=fatal_sidecar,
                    fatal_exif=fatal_exif,
                ),
            )
        raise typer.Exit(code=1)


@album_app.command("fix")
def fix_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to fix.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    refresh_jpeg: Annotated[
        bool,
        typer.Option(
            "--refresh-jpeg",
            help="Refresh {msutor}-jpg/ from {msutor}-img/ for all media_sources.",
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
    """Fix album issues. Works on all msutor types (iOS + plain).

    --refresh-jpeg: Deletes all files in {msutor}-jpg/ and re-converts
    every file from {msutor}-img/. HEIC/HEIF/DNG files are converted
    via sips; JPEG/PNG files are copied as-is.
    """
    if not refresh_jpeg:
        typer.echo(
            "No fix specified. Run photree album fix --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)

    if refresh_jpeg:
        _check_sips_or_exit()
        media_sources = discover_media_sources(album_dir)
        if not media_sources:
            typer.echo("No media_sources found in this album.", err=True)
            raise typer.Exit(code=1)

        file_count = sum(
            len(list_files(album_dir / c.img_dir))
            for c in media_sources
            if (album_dir / c.img_dir).is_dir()
        )
        progress = FileProgressBar(
            total=file_count,
            description="Converting JPEG",
            done_description="convert-jpeg",
        )
        total_converted = 0
        total_copied = 0
        total_skipped = 0
        for ms in media_sources:
            if not (album_dir / ms.img_dir).is_dir():
                continue
            prefix = f"{ms.img_dir}/"
            result = album_fixes.refresh_jpeg(
                album_dir,
                ms,
                dry_run=dry_run,
                on_file_start=lambda name, p=prefix: progress.on_start(f"{p}{name}"),
                on_file_end=lambda name, ok, p=prefix: progress.on_end(
                    f"{p}{name}", ok
                ),
            )
            total_converted += result.converted
            total_copied += result.copied
            total_skipped += result.skipped
        progress.stop()
        typer.echo(
            album_output.refresh_jpeg_summary(
                total_converted, total_copied, total_skipped
            )
        )


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
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Optimize main directories by replacing file copies with links.

    Recreates main-img/ and main-vid/ files as hard links (default),
    symbolic links, or copies depending on --link-mode. Does not touch
    main-jpg/ (those are HEIC-to-JPEG conversions that cannot be linked).

    Runs structural integrity checks first (unless --no-check): directory
    structure, file matching, checksums, sidecars, duplicates, and
    miscategorized files. Naming and EXIF checks are not performed.
    Refuses to optimize if errors are found.
    """
    if check:
        # Run checks first
        file_count = sum(
            _count_unique_media_numbers(album_dir / c.orig_img_dir, IMG_EXTENSIONS)
            + _count_unique_media_numbers(album_dir / c.orig_vid_dir, VID_EXTENSIONS)
            for c in discover_media_sources(album_dir)
        )
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

        console.print(album_output.format_album_preflight_checks(check_result))

        if not check_result.success:
            cwd = Path.cwd()
            troubleshoot = album_output.format_album_preflight_troubleshoot(
                check_result, album_dir=str(display_path(album_dir, cwd))
            )
            if troubleshoot:
                typer.echo("")
                err_console.print(troubleshoot)
            raise typer.Exit(code=1)

    # Optimize
    result = album_optimize.optimize_album(
        album_dir, link_mode=link_mode, dry_run=dry_run
    )
    typer.echo(
        album_output.optimize_summary(result.heic_count, result.mov_count, link_mode)
    )


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
    # Fix-ios operations only apply to iOS media_sources
    media_sources = [c for c in discover_media_sources(album_dir) if c.is_ios]

    if not media_sources:
        typer.echo("No iOS media_sources found in this album.", err=True)
        return

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
        total_heic = 0
        total_mov = 0
        total_jpeg_converted = 0
        total_jpeg_copied = 0
        total_jpeg_skipped = 0
        for ms in media_sources:
            result = ios_fixes.refresh_combined(
                album_dir,
                ms,
                link_mode=link_mode,
                dry_run=dry_run,
                on_stage_start=stage_progress.on_start if stage_progress else None,
                on_stage_end=stage_progress.on_end if stage_progress else None,
            )
            total_heic += result.heic.copied
            total_mov += result.mov.copied
            total_jpeg_converted += result.jpeg.converted if result.jpeg else 0
            total_jpeg_copied += result.jpeg.copied if result.jpeg else 0
            total_jpeg_skipped += result.jpeg.skipped if result.jpeg else 0
        if stage_progress:
            stage_progress.stop()
        if show_progress:
            typer.echo(
                album_output.refresh_combined_summary(
                    heic_copied=total_heic,
                    mov_copied=total_mov,
                    jpeg_converted=total_jpeg_converted,
                    jpeg_copied=total_jpeg_copied,
                    jpeg_skipped=total_jpeg_skipped,
                )
            )
    elif refresh_jpeg:
        _check_sips_or_exit()
        file_count = sum(
            len(list_files(album_dir / c.img_dir))
            for c in media_sources
            if (album_dir / c.img_dir).is_dir()
        )
        progress = (
            FileProgressBar(
                total=file_count,
                description="Converting JPEG",
                done_description="convert-jpeg",
            )
            if show_progress
            else None
        )
        total_converted = 0
        total_copied = 0
        total_skipped = 0
        for ms in media_sources:
            if not (album_dir / ms.img_dir).is_dir():
                continue
            result_jpeg = ios_fixes.refresh_jpeg(
                album_dir,
                ms,
                dry_run=dry_run,
                log_cwd=log_cwd,
                on_file_start=progress.on_start if progress else None,
                on_file_end=progress.on_end if progress else None,
            )
            total_converted += result_jpeg.converted
            total_copied += result_jpeg.copied
            total_skipped += result_jpeg.skipped
        if progress:
            progress.stop()
        if show_progress:
            typer.echo(
                album_output.refresh_jpeg_summary(
                    total_converted, total_copied, total_skipped
                )
            )

    if rm_upstream:
        for ms in media_sources:
            result_rm = ios_fixes.rm_upstream(
                album_dir, ms, dry_run=dry_run, log_cwd=log_cwd
            )
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
        for ms in media_sources:
            result_orphan = ios_fixes.rm_orphan(
                album_dir, ms, dry_run=dry_run, log_cwd=log_cwd
            )
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
        for ms in media_sources:
            result_meta = ios_fixes.rm_orphan_sidecar(
                album_dir, ms, dry_run=dry_run, log_cwd=log_cwd
            )
            if show_progress:
                typer.echo(
                    album_output.rm_orphan_sidecar_summary(result_meta.removed_by_dir)
                )

    if prefer_higher_quality_when_dups:
        for ms in media_sources:
            result_heic = ios_fixes.prefer_higher_quality_when_dups(
                album_dir, ms, dry_run=dry_run, log_cwd=log_cwd
            )
            if show_progress:
                typer.echo(
                    album_output.prefer_higher_quality_summary(
                        result_heic.removed_by_dir
                    )
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
        for ms in media_sources:
            result_miscat = fix_fn(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd)
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


@album_app.command("fix-exif")
def fix_exif_cmd(
    set_date: Annotated[
        str | None,
        typer.Option(
            "--set-date",
            help="Set EXIF date to YYYY-MM-DD (preserves original time).",
        ),
    ] = None,
    set_date_time: Annotated[
        str | None,
        typer.Option(
            "--set-date-time",
            help="Set EXIF date+time to an ISO timestamp (e.g. 2024-07-20T13:55:20).",
        ),
    ] = None,
    shift_date: Annotated[
        int | None,
        typer.Option(
            "--shift-date",
            help="Shift EXIF date by N days (e.g. -1, +2).",
        ),
    ] = None,
    shift_time: Annotated[
        int | None,
        typer.Option(
            "--shift-time",
            help="Shift EXIF time by N hours (e.g. -6, +3).",
        ),
    ] = None,
    files: Annotated[
        list[str],
        typer.Argument(
            help="File paths to fix (relative from cwd).",
        ),
    ] = [],  # noqa: B006
) -> None:
    """Fix EXIF dates on media files.

    Exactly one of --set-date, --set-date-time, --shift-date, or
    --shift-time must be specified.

    --set-date preserves the original time portion of each file's
    timestamp, only replacing the date.

    --set-date-time sets the full timestamp (date + time) on all files.

    --shift-date shifts all date tags by N days.

    --shift-time shifts all date tags by N hours.
    """
    flags = sum(
        x is not None for x in (set_date, set_date_time, shift_date, shift_time)
    )
    if flags == 0:
        err_console.print(
            "Specify exactly one of --set-date, --set-date-time,"
            " --shift-date, or --shift-time."
        )
        raise typer.Exit(code=1)
    if flags > 1:
        err_console.print(
            "--set-date, --set-date-time, --shift-date, and --shift-time"
            " are mutually exclusive."
        )
        raise typer.Exit(code=1)
    if not files:
        err_console.print("No files specified.")
        raise typer.Exit(code=1)

    if set_date is not None:
        parts = set_date.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            err_console.print(f'Invalid date "{set_date}", expected YYYY-MM-DD.')
            raise typer.Exit(code=1)

    cwd = Path.cwd()
    file_paths = [Path(f) for f in files]

    if set_date is not None:
        updated = album_exif.set_exif_date(file_paths, set_date, log_cwd=cwd)
    elif set_date_time is not None:
        updated = album_exif.set_exif_date_time(file_paths, set_date_time, log_cwd=cwd)
    elif shift_date is not None:
        updated = album_exif.shift_exif_date(file_paths, shift_date, log_cwd=cwd)
    else:
        assert shift_time is not None
        updated = album_exif.shift_exif_time(file_paths, shift_time, log_cwd=cwd)

    typer.echo(f"Done. {updated} file(s) updated.")


def _check_sips_or_exit() -> None:
    if not album_preflight.check_sips_available():
        err_console.print(album_output.sips_check(False))
        err_console.print(album_output.sips_troubleshoot())
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


@album_app.command("mv-media")
def mv_media_cmd(
    source_album: Annotated[
        Path,
        typer.Option(
            "--source-album",
            "-s",
            help="Source album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    dest_album: Annotated[
        Path,
        typer.Option(
            "--dest-album",
            "-d",
            help="Destination album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    files: Annotated[
        list[str],
        typer.Argument(
            help="Relative file paths to move (e.g. main-jpg/IMG_E3219.jpg).",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Move media files and all their variants from one album to another.

    For each specified file, resolves all associated variants by image number
    (iOS) or filename stem (plain) across the msutor's directory structure
    and moves them all. Any variant file can be used to identify the media.
    """
    cwd = Path.cwd()
    try:
        result = media_ops.move_media(
            source_album, dest_album, files, dry_run=dry_run, log_cwd=cwd
        )
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from None

    typer.echo(album_output.media_op_summary("Moved", result.files_by_dir))
    typer.echo(
        album_output.media_op_check_suggestions(
            [
                str(display_path(source_album, cwd)),
                str(display_path(dest_album, cwd)),
            ]
        )
    )


@album_app.command("rm-media")
def rm_media_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    files: Annotated[
        list[str],
        typer.Argument(
            help="Relative file paths to remove (e.g. main-jpg/IMG_E3219.jpg).",
        ),
    ] = [],  # noqa: B006
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Remove media files and all their variants from an album.

    For each specified file, resolves all associated variants by image number
    (iOS) or filename stem (plain) across the msutor's directory structure
    and removes them all. Any variant file can be used to identify the media.
    """
    if not files:
        err_console.print("No files specified.")
        raise typer.Exit(code=1)

    cwd = Path.cwd()
    try:
        result = media_ops.rm_media(album_dir, files, dry_run=dry_run, log_cwd=cwd)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from None

    typer.echo(album_output.media_op_summary("Removed", result.files_by_dir))
    typer.echo(
        album_output.media_op_check_suggestions([str(display_path(album_dir, cwd))])
    )


@album_app.command("stats")
def stats_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to analyze.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """Show disk usage and content statistics for a single album."""
    try:
        result = album_stats.compute_album_stats(album_dir)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from None

    console.print(album_output.format_album_stats(result))
