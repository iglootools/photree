"""``photree album fix-ios`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import album_app
from .helpers import _check_sips_or_exit
from .. import (
    output as album_output,
    preflight as album_preflight,
)
from ..ios_fixes import (
    FixIosValidationError,
    run_fix_ios,
    validate_fix_flags,
)
from ...clicommons.options import (
    DRY_RUN_OPTION,
    LINK_MODE_OPTION,
    MV_MISCATEGORIZED_OPTION,
    PREFER_HIGHER_QUALITY_OPTION,
    REFRESH_BROWSABLE_OPTION,
    REFRESH_JPEG_OPTION,
    RM_MISCATEGORIZED_OPTION,
    RM_MISCATEGORIZED_SAFE_OPTION,
    RM_ORPHAN_OPTION,
    RM_ORPHAN_SIDECAR_OPTION,
    RM_UPSTREAM_OPTION,
)
from ...clicommons.progress import FileProgressBar, StageProgressBar
from ...fs import (
    discover_media_sources,
    list_files,
    resolve_link_mode,
)


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
    link_mode: LINK_MODE_OPTION = None,
    refresh_browsable: REFRESH_BROWSABLE_OPTION = False,
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    prefer_higher_quality_when_dups: PREFER_HIGHER_QUALITY_OPTION = False,
    rm_orphan_sidecar: RM_ORPHAN_SIDECAR_OPTION = False,
    rm_miscategorized: RM_MISCATEGORIZED_OPTION = False,
    rm_miscategorized_safe: RM_MISCATEGORIZED_SAFE_OPTION = False,
    mv_miscategorized: MV_MISCATEGORIZED_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix iOS album issues. At least one fix flag must be specified.

    Available fixes:

    --refresh-browsable: Deletes main-img/, main-vid/, and
    main-jpg/, then rebuilds main-img and main-vid from
    orig/edit sources. If main-img/ is created, also regenerates
    main-jpg/ via HEIC→JPEG conversion.

    --refresh-jpeg: Deletes all files in main-jpg/ and re-converts
    every file from main-img/. HEIC files are converted via sips;
    JPEG/PNG files are copied as-is.

    --rm-upstream: Propagates deletions from browsing directories to
    upstream directories. Files deleted from main-jpg/ are removed
    from main-img/, edit-img/, and orig-img/. Files deleted
    from main-vid/ are removed from edit-vid/ and orig-vid/.

    --rm-orphan: Deletes edited and main files whose image number
    has no corresponding original file in orig-img/ or orig-vid/.

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
    cwd = Path.cwd()

    album_type = album_preflight.detect_album_type(album_dir)
    if album_type != album_preflight.AlbumType.IOS:
        typer.echo(
            f"Album type is '{album_type.value}', but fix-ios only supports iOS albums.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        validate_fix_flags(
            refresh_browsable=refresh_browsable,
            refresh_jpeg=refresh_jpeg,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
            rm_orphan_sidecar=rm_orphan_sidecar,
            prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
            rm_miscategorized=rm_miscategorized,
            rm_miscategorized_safe=rm_miscategorized_safe,
            mv_miscategorized=mv_miscategorized,
        )
    except FixIosValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if refresh_browsable or refresh_jpeg:
        _check_sips_or_exit()

    stage_progress = (
        StageProgressBar(
            total=4,
            labels={
                "delete": "Deleting main directories",
                "refresh-heic": "Rebuilding main-img",
                "refresh-mov": "Rebuilding main-vid",
                "refresh-jpeg": "Converting HEIC to JPEG",
            },
        )
        if refresh_browsable
        else None
    )

    file_count = 0
    if refresh_jpeg:
        media_sources = discover_media_sources(album_dir)
        file_count = sum(
            len(list_files(album_dir / c.img_dir))
            for c in media_sources
            if c.is_ios and (album_dir / c.img_dir).is_dir()
        )
    file_progress = (
        FileProgressBar(
            total=file_count,
            description="Converting JPEG",
            done_description="convert-jpeg",
        )
        if refresh_jpeg
        else None
    )

    result = run_fix_ios(
        album_dir,
        link_mode=resolve_link_mode(link_mode, album_dir),
        dry_run=dry_run,
        log_cwd=cwd,
        refresh_browsable_flag=refresh_browsable,
        refresh_jpeg_flag=refresh_jpeg,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
        on_refresh_browsable_stage_start=stage_progress.on_start
        if stage_progress
        else None,
        on_refresh_browsable_stage_end=stage_progress.on_end
        if stage_progress
        else None,
        on_refresh_jpeg_file_start=file_progress.on_start if file_progress else None,
        on_refresh_jpeg_file_end=file_progress.on_end if file_progress else None,
    )

    if stage_progress:
        stage_progress.stop()
    if file_progress:
        file_progress.stop()

    for line in album_output.format_fix_ios_result(result):
        typer.echo(line)
