"""``photree album check`` command."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.options import (
    CHECK_DATE_PART_COLLISION_OPTION,
    CHECK_EXIF_DATE_MATCH_OPTION,
    CHECK_NAMING_OPTION,
    CHECKSUM_OPTION,
    FATAL_EXIF_DATE_MATCH_OPTION,
    FATAL_SIDECAR_OPTION,
    FATAL_WARNINGS_OPTION,
)
from ...clihelpers.progress import SilentProgressBar
from ...common.exif import exiftool_session
from ...common.fs import count_unique_media_numbers, display_path
from .. import (
    check as album_check,
)
from .. import (
    naming as album_naming,
)
from ..check import output as preflight_output
from ..exif_cache.refresh import refresh_exif_cache as refresh_album_exif_cache
from ..store.album_discovery import discover_albums
from ..store.media_sources_discovery import (
    MediaSourceConflictError,
    discover_media_sources,
    find_media_source_conflicts,
)
from ..store.protocol import IMG_EXTENSIONS, VID_EXTENSIONS
from . import album_app
from .helpers import format_media_source_conflict


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
    checksum: CHECKSUM_OPTION = True,
    fatal_warnings: FATAL_WARNINGS_OPTION = False,
    fatal_sidecar_arg: FATAL_SIDECAR_OPTION = False,
    fatal_exif_date_match: FATAL_EXIF_DATE_MATCH_OPTION = True,
    check_naming: CHECK_NAMING_OPTION = True,
    check_exif_date_match: CHECK_EXIF_DATE_MATCH_OPTION = True,
    check_date_part_collision: CHECK_DATE_PART_COLLISION_OPTION = True,
    refresh_exif_cache: Annotated[
        bool,
        typer.Option(
            "--refresh-exif-cache",
            help="Refresh the EXIF timestamp cache before checking.",
        ),
    ] = False,
) -> None:
    """Check system prerequisites, album directory structure, and file integrity."""
    cwd = Path.cwd()
    _require_no_media_source_conflict(album_dir, cwd)
    if refresh_exif_cache:
        refresh_album_exif_cache(album_dir)

    result = _run_check(
        album_dir,
        checksum=checksum,
        check_naming=check_naming,
        check_exif_date_match=check_exif_date_match,
    )

    fatal_sidecar = fatal_warnings or fatal_sidecar_arg
    fatal_exif = fatal_warnings or fatal_exif_date_match
    album_dir_display = str(display_path(album_dir, cwd))

    console.print(
        preflight_output.format_album_preflight_checks(
            result,
            fatal_sidecar=fatal_sidecar,
            fatal_exif=fatal_exif,
            album_dir=album_dir_display,
        )
    )
    # Evaluated before the failure test (not short-circuited by it) so the
    # collision report is printed even when the album check already failed.
    collisions_ok = not (check_naming and check_date_part_collision) or (
        _check_sibling_date_collisions(album_dir)
    )
    if (
        not result.success
        or result.has_fatal_warnings(fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif)
        or not collisions_ok
    ):
        _print_troubleshooting(
            result,
            album_dir_display=album_dir_display,
            fatal_sidecar=fatal_sidecar,
            fatal_exif=fatal_exif,
        )
        raise typer.Exit(code=1)


def _require_no_media_source_conflict(album_dir: Path, cwd: Path) -> None:
    """Report an iOS/std media source name clash, which no other check survives."""
    conflicts = find_media_source_conflicts(album_dir)
    if conflicts:
        err_console.print(
            format_media_source_conflict(
                MediaSourceConflictError(album_dir, conflicts), cwd
            ),
            markup=False,
        )
        raise typer.Exit(code=1)


def _count_media_items(album_dir: Path) -> int:
    """Count unique media numbers across all media sources' orig dirs."""
    return sum(
        count_unique_media_numbers(album_dir / c.orig_img_dir, IMG_EXTENSIONS)
        + count_unique_media_numbers(album_dir / c.orig_vid_dir, VID_EXTENSIONS)
        for c in discover_media_sources(album_dir)
    )


def _run_check(
    album_dir: Path,
    *,
    checksum: bool,
    check_naming: bool,
    check_exif_date_match: bool,
) -> album_check.AlbumPreflightResult:
    file_count = _count_media_items(album_dir)
    progress_cm = (
        SilentProgressBar(total=file_count, description="Checking")
        if file_count > 0
        else nullcontext(None)
    )
    with (
        exiftool_session(enabled=check_exif_date_match) as exiftool,
        progress_cm as progress,
    ):
        return album_check.run_album_preflight(
            album_dir,
            sips_available=album_check.check_sips_available(),
            exiftool=exiftool,
            checksum=checksum,
            check_naming_flag=check_naming,
            on_file_checked=progress.advance if progress is not None else None,
        )


def _check_sibling_date_collisions(album_dir: Path) -> bool:
    """Print date collisions against sibling albums; return whether there are none."""
    parsed_siblings = [
        (a.name, parsed)
        for a in discover_albums(album_dir.parent)
        if (parsed := album_naming.parse_album_name(a.name)) is not None
    ]
    batch_naming = album_naming.check_batch_date_collisions(parsed_siblings)
    console.print(preflight_output.format_batch_naming_issues(batch_naming))
    return batch_naming.success


def _print_troubleshooting(
    result: album_check.AlbumPreflightResult,
    *,
    album_dir_display: str,
    fatal_sidecar: bool,
    fatal_exif: bool,
) -> None:
    troubleshoot = preflight_output.format_album_preflight_troubleshoot(
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
            preflight_output.format_fatal_warnings(
                result, fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
            ),
        )
