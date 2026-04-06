"""``photree album check`` command."""

from __future__ import annotations

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
from ...common.fs import count_unique_media_numbers, display_path
from .. import (
    check as album_check,
    naming as album_naming,
)
from ..check import output as preflight_output
from ..store.album_discovery import discover_albums
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import IMG_EXTENSIONS, VID_EXTENSIONS
from . import album_app


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
) -> None:
    """Check system prerequisites, album directory structure, and file integrity."""
    # Count unique media numbers across all media_sources' orig dirs
    file_count = sum(
        count_unique_media_numbers(album_dir / c.orig_img_dir, IMG_EXTENSIONS)
        + count_unique_media_numbers(album_dir / c.orig_vid_dir, VID_EXTENSIONS)
        for c in discover_media_sources(album_dir)
    )
    progress_cm = (
        SilentProgressBar(total=max(file_count, 1), description="Checking")
        if file_count > 0
        else None
    )

    if progress_cm is not None:
        with progress_cm as progress:
            result = album_check.run_album_preflight(
                album_dir,
                checksum=checksum,
                check_naming_flag=check_naming,
                check_exif_date_match=check_exif_date_match,
                on_file_checked=progress.advance,
            )
    else:
        result = album_check.run_album_preflight(
            album_dir,
            checksum=checksum,
            check_naming_flag=check_naming,
            check_exif_date_match=check_exif_date_match,
            on_file_checked=None,
        )

    fatal_sidecar = fatal_warnings or fatal_sidecar_arg
    fatal_exif = fatal_warnings or fatal_exif_date_match

    cwd = Path.cwd()
    album_dir_display = str(display_path(album_dir, cwd))

    console.print(
        preflight_output.format_album_preflight_checks(
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
        console.print(preflight_output.format_batch_naming_issues(batch_naming))
        if not batch_naming.success:
            failed = True

    if failed:
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
                    result,
                    fatal_sidecar=fatal_sidecar,
                    fatal_exif=fatal_exif,
                ),
            )
        raise typer.Exit(code=1)
