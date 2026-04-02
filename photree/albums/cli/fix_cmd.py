"""``photree albums fix`` command."""

from __future__ import annotations

from typing import Annotated

import typer

from . import AlbumDirOption, DirOption, albums_app
from ...album.cli.helpers import _check_sips_or_exit
from ...album.fix import FixValidationError
from ...clihelpers.options import (
    DRY_RUN_OPTION,
    LINK_MODE_REQUIRED_OPTION,
    REFRESH_BROWSABLE_OPTION,
    REFRESH_JPEG_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from ...fs import LinkMode
from .batch_ops import resolve_check_batch_albums, run_batch_fix


@albums_app.command("fix")
def fix_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    fix_id: Annotated[
        bool,
        typer.Option("--id", help="Generate missing album IDs (.photree/album.yaml)."),
    ] = False,
    new_id: Annotated[
        bool,
        typer.Option("--new-id", help="Regenerate album IDs (replaces existing IDs)."),
    ] = False,
    link_mode: LINK_MODE_REQUIRED_OPTION = LinkMode.HARDLINK,
    refresh_browsable: REFRESH_BROWSABLE_OPTION = False,
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix all albums under a directory or from an explicit list."""
    try:
        from ...album.fix import validate_fix_flags

        validate_fix_flags(
            fix_id=fix_id,
            new_id=new_id,
            refresh_browsable=refresh_browsable,
            refresh_jpeg=refresh_jpeg,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
        )
    except FixValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if refresh_browsable or refresh_jpeg:
        _check_sips_or_exit()

    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        link_mode=link_mode,
        refresh_browsable=refresh_browsable,
        refresh_jpeg=refresh_jpeg,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        dry_run=dry_run,
    )
