"""``photree album fix`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import album_app
from .helpers import _check_sips_or_exit
from .. import fix as album_fixes
from ..fix.output import format_fix_result
from ..fix import FixValidationError
from ...clihelpers.options import (
    DRY_RUN_OPTION,
    LINK_MODE_OPTION,
    REFRESH_BROWSABLE_OPTION,
    REFRESH_JPEG_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from ...clihelpers.progress import FileProgressBar, StageProgressBar
from ...fs import (
    AlbumMetadata,
    discover_media_sources,
    format_album_external_id,
    generate_album_id,
    list_files,
    load_album_metadata,
    resolve_link_mode,
    save_album_metadata,
)


@album_app.command("fix")
def fix_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to fix.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    fix_id: Annotated[
        bool,
        typer.Option(
            "--id",
            help="Generate missing album ID (.photree/album.yaml).",
        ),
    ] = False,
    new_id: Annotated[
        bool,
        typer.Option(
            "--new-id",
            help="Regenerate album ID (replaces existing ID).",
        ),
    ] = False,
    link_mode: LINK_MODE_OPTION = None,
    refresh_browsable: REFRESH_BROWSABLE_OPTION = False,
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix album issues. Works on all media source types (iOS + std).

    --id: Generates a missing album ID in .photree/album.yaml. Skips
    albums that already have an ID.

    --new-id: Regenerates the album ID, replacing any existing one.

    --refresh-browsable: Deletes {name}-img/, {name}-vid/, and
    {name}-jpg/, then rebuilds {name}-img and {name}-vid from
    orig/edit sources. If {name}-img/ is created, also regenerates
    {name}-jpg/ via HEIC->JPEG conversion.

    --refresh-jpeg: Deletes all files in {name}-jpg/ and re-converts
    every file from {name}-img/. HEIC/HEIF/DNG files are converted
    via sips; JPEG/PNG files are copied as-is.

    --rm-upstream: Propagates deletions from browsing directories to
    upstream directories.

    --rm-orphan: Deletes edited and main files whose key has no
    corresponding original file in orig-img/ or orig-vid/.
    """
    cwd = Path.cwd()

    try:
        album_fixes.validate_fix_flags(
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

    if fix_id or new_id:
        metadata = load_album_metadata(album_dir)
        match (metadata, new_id, dry_run):
            case (AlbumMetadata() as m, False, _):
                typer.echo(f"Album already has an ID: {format_album_external_id(m.id)}")
            case (_, _, True):
                typer.echo("[dry-run] Would generate album ID.")
            case _:
                generated_id = generate_album_id()
                save_album_metadata(album_dir, AlbumMetadata(id=generated_id))
                typer.echo(
                    f"Generated album ID: {format_album_external_id(generated_id)}"
                )

    any_archive_op = refresh_browsable or refresh_jpeg or rm_upstream or rm_orphan
    if not any_archive_op:
        return

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
            if (album_dir / c.img_dir).is_dir()
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

    result = album_fixes.run_fix(
        album_dir,
        link_mode=resolve_link_mode(link_mode, album_dir),
        dry_run=dry_run,
        log_cwd=cwd,
        refresh_browsable_flag=refresh_browsable,
        refresh_jpeg_flag=refresh_jpeg,
        rm_upstream_flag=rm_upstream,
        rm_orphan_flag=rm_orphan,
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

    for line in format_fix_result(result):
        typer.echo(line)
