"""``photree albums fix`` command."""

from __future__ import annotations

from typing import Annotated

import typer

from . import AlbumDirOption, DirOption, albums_app
from ...album.cli.helpers import _check_sips_or_exit
from ...clicommons.options import DRY_RUN_OPTION, REFRESH_JPEG_OPTION
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
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix all albums under a directory or from an explicit list."""
    if not fix_id and not new_id and not refresh_jpeg:
        typer.echo(
            "No fix specified. Run photree albums fix --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)

    if refresh_jpeg:
        _check_sips_or_exit()

    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        refresh_jpeg=refresh_jpeg,
        dry_run=dry_run,
    )
