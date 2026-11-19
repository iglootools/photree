from typing import Annotated

import typer

from ...album.fix import FixValidationError, validate_fix_flags
from ...clihelpers.console import err_console
from ...clihelpers.options import (
    DRY_RUN_OPTION,
    FORCE_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from ...clihelpers.runtime import runtime_of
from ..batchcli.fix import run_batch_fix
from ..batchcli.resolution import resolve_check_batch_albums
from . import ALBUM_DIR_OPTION, DIR_OPTION, app


@app.command("fix")
def fix_cmd(
    ctx: typer.Context,
    base_dir: DIR_OPTION = None,
    album_dirs: ALBUM_DIR_OPTION = None,
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
    """Fix all albums under a directory or from an explicit list."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    try:
        validate_fix_flags(
            fix_id=fix_id,
            new_id=new_id,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
        )
    except FixValidationError as exc:
        err_console.print(
            f"{exc}\nRun 'photree albums fix --help' for the available fixes.",
            markup=False,
        )
        raise typer.Exit(code=1) from exc

    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs, cwd=cwd)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        dry_run=dry_run,
        force=force,
        cwd=cwd,
    )
