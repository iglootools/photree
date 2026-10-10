"""``photree gallery fix`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...album.fix import FixValidationError, validate_fix_flags
from ...albums.batchcli.fix import run_batch_fix
from ...albums.batchcli.resolution import resolve_check_batch_albums
from ...clihelpers.console import err_console
from ...clihelpers.options import (
    DRY_RUN_OPTION,
    FORCE_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from ...clihelpers.resolution import resolve_gallery_or_exit
from . import gallery_app


@gallery_app.command("fix")
def fix_cmd(
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
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
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    force: FORCE_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix all albums in the gallery."""
    try:
        validate_fix_flags(
            fix_id=fix_id,
            new_id=new_id,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
        )
    except FixValidationError as exc:
        err_console.print(
            f"{exc}\nRun 'photree gallery fix --help' for the available fixes.",
            markup=False,
        )
        raise typer.Exit(code=1) from exc

    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        dry_run=dry_run,
        force=force,
    )
