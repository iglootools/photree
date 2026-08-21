"""``albums check`` / ``gallery check`` wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from ....album import check as album_check
from ....album.check import output as preflight_output
from ....album.check.output import batch_check_summary
from ....album.id import format_album_external_id, format_image_external_id
from ....album.naming import BatchNamingResult
from ....clihelpers.console import console, err_console
from ....clihelpers.progress import BatchProgressBar
from ....common.exif import try_start_exiftool
from ....fsprotocol import LinkMode, resolve_link_mode
from ...cmd_handler.check import batch_check
from ..ops import make_display_fn
from .failures import investigate_commands


def run_batch_check(
    albums: list[Path],
    display_base: Path | None,
    *,
    checksum: bool = True,
    fatal_warnings: bool = False,
    fatal_sidecar_arg: bool = False,
    fatal_exif_date_match: bool = True,
    check_naming: bool = True,
    check_date_part_collision: bool = True,
    check_exif_date_match: bool = True,
    refresh_exif_cache: bool = False,
) -> None:
    """Shared implementation for gallery check / albums check."""
    cwd = Path.cwd()

    # System checks (once)
    sips_available = album_check.check_sips_available()
    exiftool = try_start_exiftool() if check_exif_date_match else None
    exiftool_available = exiftool is not None
    typer.echo("System Checks:")
    console.print(
        preflight_output.batch_system_checks(
            sips_available=sips_available, exiftool_available=exiftool_available
        )
    )
    if not sips_available:
        typer.echo("")
        err_console.print(preflight_output.sips_troubleshoot())
        raise typer.Exit(code=1)

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if refresh_exif_cache:
        from ....album.exif_cache.refresh import refresh_exif_cache as _refresh_exif

        typer.echo("\nRefreshing EXIF cache...")
        for album_dir in albums:
            _refresh_exif(album_dir, exiftool=exiftool)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")
    else:
        typer.echo("")

    fatal_sidecar = fatal_warnings or fatal_sidecar_arg
    fatal_exif = fatal_warnings or fatal_exif_date_match
    resolved_link_mode = (
        resolve_link_mode(None, albums[0]) if albums else LinkMode.HARDLINK
    )

    with BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    ) as progress:
        try:
            result = batch_check(
                albums,
                sips_available=sips_available,
                exiftool=exiftool,
                link_mode=resolved_link_mode,
                checksum=checksum,
                fatal_sidecar=fatal_sidecar,
                fatal_exif=fatal_exif,
                check_naming=check_naming,
                check_date_part_collision=check_date_part_collision,
                display_fn=make_display_fn(display_base, cwd),
                on_start=progress.on_start,
                on_end=lambda name, success, errors, warnings: progress.on_end(
                    name,
                    success=success,
                    error_labels=errors,
                    warning_labels=warnings,
                ),
            )
        finally:
            if exiftool is not None:
                exiftool.__exit__(None, None, None)

    # Cross-album checks (with spinner — duplicate ID scan reads all metadata)
    from ....clihelpers.progress import run_with_spinner

    cross_album = run_with_spinner(
        "Running cross-album checks...",
        lambda: _compute_cross_album_checks(
            albums,
            check_naming=check_naming,
            check_date_part_collision=check_date_part_collision,
        ),
    )

    typer.echo("\nCross-album checks:")
    if cross_album.naming_result is not None:
        console.print(
            preflight_output.format_batch_naming_issues(cross_album.naming_result)
        )

    if cross_album.duplicate_ids:
        err_console.print(
            preflight_output.duplicate_ids_report(
                "album", cross_album.duplicate_ids, cwd, format_album_external_id
            )
        )
    else:
        console.print(preflight_output.no_duplicate_ids_line("album"))

    if cross_album.duplicate_media_ids:
        err_console.print(
            preflight_output.duplicate_ids_report(
                "media", cross_album.duplicate_media_ids, cwd, format_image_external_id
            )
        )
    else:
        console.print(preflight_output.no_duplicate_ids_line("media"))

    # Merge cross-album failures into result
    if cross_album.failed_albums:
        result.failed_albums.extend(cross_album.failed_albums)

    # Summary
    console.print(
        batch_check_summary(result.passed, len(result.failed_albums), result.warned)
    )

    if result.failed_albums:
        err_console.print(
            investigate_commands(
                "check",
                sorted(set(result.failed_albums)),
                cwd,
                extra_flags=preflight_output.batch_check_retry_flags(
                    fatal_warnings=fatal_warnings,
                    fatal_sidecar=fatal_sidecar_arg,
                    fatal_exif_date_match=fatal_exif_date_match,
                ),
            )
        )
        raise typer.Exit(code=1)


@dataclass(frozen=True)
class _CrossAlbumResult:
    naming_result: BatchNamingResult | None
    duplicate_ids: dict[str, list[Path]]
    duplicate_media_ids: dict[str, list[Path]]
    failed_albums: list[Path]


def _compute_cross_album_checks(
    albums: list[Path],
    *,
    check_naming: bool,
    check_date_part_collision: bool,
) -> _CrossAlbumResult:
    """Run cross-album checks (date collisions, duplicate IDs)."""
    from ....album import naming as album_naming
    from ...index import find_duplicate_album_ids
    from ...media_index import find_duplicate_media_ids

    failed: list[Path] = []

    naming_result = None
    if check_naming and check_date_part_collision:
        parsed_albums = [
            (album.name, parsed)
            for album in albums
            if (parsed := album_naming.parse_album_name(album.name)) is not None
        ]
        naming_result = album_naming.check_batch_date_collisions(parsed_albums)
        if not naming_result.success:
            colliding_names = {
                name for _, names in naming_result.date_collisions for name in names
            }
            failed.extend(a for a in albums if a.name in colliding_names)

    duplicate_ids = find_duplicate_album_ids(albums)
    if duplicate_ids:
        failed.extend(p for paths in duplicate_ids.values() for p in paths)

    duplicate_media_ids = find_duplicate_media_ids(albums)
    if duplicate_media_ids:
        failed.extend(p for paths in duplicate_media_ids.values() for p in paths)

    return _CrossAlbumResult(
        naming_result=naming_result,
        duplicate_ids=duplicate_ids,
        duplicate_media_ids=duplicate_media_ids,
        failed_albums=failed,
    )
