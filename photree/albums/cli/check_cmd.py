from typing import Annotated

import typer

from photree.albums.batchcli.check import run_batch_check
from photree.albums.batchcli.resolution import resolve_check_batch_albums
from photree.albums.cli import ALBUM_DIR_OPTION, DIR_OPTION, app
from photree.clihelpers.options import (
    CHECK_DATE_PART_COLLISION_OPTION,
    CHECK_EXIF_DATE_MATCH_OPTION,
    CHECK_NAMING_OPTION,
    CHECKSUM_OPTION,
    FATAL_EXIF_DATE_MATCH_OPTION,
    FATAL_SIDECAR_OPTION,
    FATAL_WARNINGS_OPTION,
)
from photree.clihelpers.runtime import runtime_of


@app.command("check")
def check_cmd(
    ctx: typer.Context,
    base_dir: DIR_OPTION = None,
    album_dirs: ALBUM_DIR_OPTION = None,
    checksum: CHECKSUM_OPTION = True,
    fatal_warnings: FATAL_WARNINGS_OPTION = False,
    fatal_sidecar_arg: FATAL_SIDECAR_OPTION = False,
    fatal_exif_date_match: FATAL_EXIF_DATE_MATCH_OPTION = True,
    check_naming: CHECK_NAMING_OPTION = True,
    check_date_part_collision: CHECK_DATE_PART_COLLISION_OPTION = True,
    check_exif_date_match: CHECK_EXIF_DATE_MATCH_OPTION = True,
    refresh_exif_cache: Annotated[
        bool,
        typer.Option(
            "--refresh-exif-cache",
            help="Refresh the EXIF timestamp cache before checking.",
        ),
    ] = False,
) -> None:
    """Check all albums under a directory or from an explicit list."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs, cwd=cwd)
    run_batch_check(
        albums,
        display_base,
        checksum=checksum,
        fatal_warnings=fatal_warnings,
        fatal_sidecar_arg=fatal_sidecar_arg,
        fatal_exif_date_match=fatal_exif_date_match,
        check_naming=check_naming,
        check_date_part_collision=check_date_part_collision,
        check_exif_date_match=check_exif_date_match,
        refresh_exif_cache=refresh_exif_cache,
        which=runtime.which,
        cwd=cwd,
    )
