"""``photree gallery fix`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clihelpers.options import (
    DRY_RUN_OPTION,
    LINK_MODE_OPTION,
    REFRESH_BROWSABLE_OPTION,
    REFRESH_JPEG_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from ...album.cli.helpers import _check_sips_or_exit
from ...album.fix import FixValidationError
from ...albums.cli.batch_ops import resolve_check_batch_albums, run_batch_fix
from ...fsprotocol import resolve_link_mode
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
    link_mode: LINK_MODE_OPTION = None,
    refresh_browsable: REFRESH_BROWSABLE_OPTION = False,
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix all albums in the gallery."""
    from ...album.fix import validate_fix_flags

    try:
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

    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        link_mode=resolve_link_mode(link_mode, resolved),
        refresh_browsable=refresh_browsable,
        refresh_jpeg=refresh_jpeg,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        dry_run=dry_run,
    )
