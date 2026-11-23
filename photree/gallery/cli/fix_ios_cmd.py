"""The ``photree gallery fix-ios`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.fix.ios import FixIosValidationError, validate_fix_flags
from photree.albums.batchcli.fix import run_batch_fix_ios
from photree.albums.batchcli.resolution import resolve_gallery_albums
from photree.clihelpers.options import (
    DRY_RUN_OPTION,
    MV_MISCATEGORIZED_OPTION,
    PREFER_HIGHER_QUALITY_OPTION,
    RM_MISCATEGORIZED_OPTION,
    RM_MISCATEGORIZED_SAFE_OPTION,
    RM_ORPHAN_SIDECAR_OPTION,
)
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import invalid_fix_error
from photree.gallery.cli.app import app


@app.command("fix-ios")
def fix_ios_cmd(
    ctx: typer.Context,
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    *,
    prefer_higher_quality_when_dups: PREFER_HIGHER_QUALITY_OPTION = False,
    rm_orphan_sidecar: RM_ORPHAN_SIDECAR_OPTION = False,
    rm_miscategorized: RM_MISCATEGORIZED_OPTION = False,
    rm_miscategorized_safe: RM_MISCATEGORIZED_SAFE_OPTION = False,
    mv_miscategorized: MV_MISCATEGORIZED_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Apply fix-ios to all iOS albums in the gallery."""
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
        raise invalid_fix_error(exc, command="gallery fix-ios") from exc
    resolved = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    albums, display_base = resolve_gallery_albums(resolved)
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
