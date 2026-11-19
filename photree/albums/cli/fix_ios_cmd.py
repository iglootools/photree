import typer

from ...album.fix.ios import FixIosValidationError, validate_fix_flags
from ...clihelpers.console import err_console
from ...clihelpers.options import (
    DRY_RUN_OPTION,
    MV_MISCATEGORIZED_OPTION,
    PREFER_HIGHER_QUALITY_OPTION,
    RM_MISCATEGORIZED_OPTION,
    RM_MISCATEGORIZED_SAFE_OPTION,
    RM_ORPHAN_SIDECAR_OPTION,
)
from ...clihelpers.runtime import runtime_of
from ..batchcli.fix import run_batch_fix_ios
from ..batchcli.resolution import resolve_batch_albums
from . import ALBUM_DIR_OPTION, DIR_OPTION, app


@app.command("fix-ios")
def fix_ios_cmd(
    ctx: typer.Context,
    base_dir: DIR_OPTION = None,
    album_dirs: ALBUM_DIR_OPTION = None,
    prefer_higher_quality_when_dups: PREFER_HIGHER_QUALITY_OPTION = False,
    rm_orphan_sidecar: RM_ORPHAN_SIDECAR_OPTION = False,
    rm_miscategorized: RM_MISCATEGORIZED_OPTION = False,
    rm_miscategorized_safe: RM_MISCATEGORIZED_SAFE_OPTION = False,
    mv_miscategorized: MV_MISCATEGORIZED_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Apply fix-ios to all iOS albums under a directory or from an explicit list."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    try:
        validate_fix_flags(
            rm_orphan_sidecar=rm_orphan_sidecar,
            prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
            rm_miscategorized=rm_miscategorized,
            rm_miscategorized_safe=rm_miscategorized_safe,
            mv_miscategorized=mv_miscategorized,
        )
    except FixIosValidationError as exc:
        err_console.print(
            f"{exc}\nRun 'photree albums fix-ios --help' for the available fixes.",
            markup=False,
        )
        raise typer.Exit(code=1) from exc

    albums, display_base = resolve_batch_albums(base_dir, album_dirs, cwd=cwd)
    run_batch_fix_ios(
        albums,
        display_base,
        dry_run=dry_run,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
        cwd=cwd,
    )
