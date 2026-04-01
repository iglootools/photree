"""``photree gallery fix`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clicommons.options import (
    DRY_RUN_OPTION,
    REFRESH_JPEG_OPTION,
)
from ...album.cli.helpers import _check_sips_or_exit
from ...albums.cli.batch_ops import resolve_check_batch_albums, run_batch_fix
from .ops import resolve_gallery_or_exit


@gallery_app.command("fix")
def fix_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
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
    """Fix all albums in the gallery."""
    if not fix_id and not new_id and not refresh_jpeg:
        typer.echo(
            "No fix specified. Run photree gallery fix --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)

    if refresh_jpeg:
        _check_sips_or_exit()

    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        refresh_jpeg=refresh_jpeg,
        dry_run=dry_run,
    )
