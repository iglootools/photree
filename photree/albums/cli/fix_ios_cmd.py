"""``photree albums fix-ios`` command."""

from __future__ import annotations

import typer

from . import AlbumDirOption, DirOption, albums_app
from ...album.fix.ios import FixIosValidationError, validate_fix_flags
from ...clicommons.options import (
    DRY_RUN_OPTION,
    MV_MISCATEGORIZED_OPTION,
    PREFER_HIGHER_QUALITY_OPTION,
    RM_MISCATEGORIZED_OPTION,
    RM_MISCATEGORIZED_SAFE_OPTION,
    RM_ORPHAN_SIDECAR_OPTION,
)
from .batch_ops import resolve_batch_albums, run_batch_fix_ios


@albums_app.command("fix-ios")
def fix_ios_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    prefer_higher_quality_when_dups: PREFER_HIGHER_QUALITY_OPTION = False,
    rm_orphan_sidecar: RM_ORPHAN_SIDECAR_OPTION = False,
    rm_miscategorized: RM_MISCATEGORIZED_OPTION = False,
    rm_miscategorized_safe: RM_MISCATEGORIZED_SAFE_OPTION = False,
    mv_miscategorized: MV_MISCATEGORIZED_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Apply fix-ios to all iOS albums under a directory or from an explicit list."""
    try:
        validate_fix_flags(
            rm_orphan_sidecar=rm_orphan_sidecar,
            prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
            rm_miscategorized=rm_miscategorized,
            rm_miscategorized_safe=rm_miscategorized_safe,
            mv_miscategorized=mv_miscategorized,
        )
    except FixIosValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    albums, display_base = resolve_batch_albums(base_dir, album_dirs)
    run_batch_fix_ios(
        albums,
        display_base,
        dry_run=dry_run,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
    )
