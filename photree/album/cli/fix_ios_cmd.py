"""``photree album fix-ios`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.options import (
    DRY_RUN_OPTION,
    MV_MISCATEGORIZED_OPTION,
    PREFER_HIGHER_QUALITY_OPTION,
    RM_MISCATEGORIZED_OPTION,
    RM_MISCATEGORIZED_SAFE_OPTION,
    RM_ORPHAN_SIDECAR_OPTION,
)
from ..store.media_sources_discovery import discover_media_sources
from ..fix.ios import (
    FixIosValidationError,
    run_fix_ios,
    validate_fix_flags,
)
from ..fix.ios.output import format_fix_ios_result
from . import album_app


@album_app.command("fix-ios")
def fix_ios_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="iOS album directory to fix.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    prefer_higher_quality_when_dups: PREFER_HIGHER_QUALITY_OPTION = False,
    rm_orphan_sidecar: RM_ORPHAN_SIDECAR_OPTION = False,
    rm_miscategorized: RM_MISCATEGORIZED_OPTION = False,
    rm_miscategorized_safe: RM_MISCATEGORIZED_SAFE_OPTION = False,
    mv_miscategorized: MV_MISCATEGORIZED_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix iOS-specific album issues. At least one fix flag must be specified.

    Available fixes:

    --rm-orphan-sidecar: Deletes AAE sidecar files in orig-img/,
    edit-img/, orig-vid/, and edit-vid/ that have no matching
    media file.

    --prefer-higher-quality-when-dups: When multiple format variants exist for the
    same image number (e.g. DNG + HEIC, or HEIC + JPG), deletes the lower-quality
    file from all image subdirectories. Priority: DNG > HEIC > JPG/PNG.

    --rm-miscategorized: Deletes files that are in the wrong directory
    (e.g. edited files in orig-img/ or original files in edit-img/).

    --rm-miscategorized-safe: Like --rm-miscategorized, but only deletes
    a miscategorized file if it already exists in the correct directory.
    Safe to run when you're unsure whether the file was copied or moved.

    --mv-miscategorized: Moves files to the correct directory instead of
    deleting them (e.g. edited files from orig-img/ to edit-img/).
    """
    media_sources = discover_media_sources(album_dir)
    if not any(ms.is_ios for ms in media_sources):
        typer.echo(
            "No iOS media sources found. fix-ios only supports iOS albums.",
            err=True,
        )
        raise typer.Exit(code=1)

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

    result = run_fix_ios(
        album_dir,
        dry_run=dry_run,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
    )

    for line in format_fix_ios_result(result):
        typer.echo(line)
