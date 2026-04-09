"""``photree albums refresh`` command."""

from __future__ import annotations

from typing import Annotated

import typer

from ...clihelpers.options import DRY_RUN_OPTION
from . import AlbumDirOption, DirOption, albums_app
from .batch_ops import run_batch_refresh
from .ops import resolve_check_batch_albums


@albums_app.command("refresh")
def refresh_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    dry_run: DRY_RUN_OPTION = False,
    refresh_browsable: Annotated[
        bool,
        typer.Option(
            "--refresh-browsable",
            help="Force rebuild all browsable directories (skip check gate).",
        ),
    ] = False,
    refresh_jpeg: Annotated[
        bool,
        typer.Option(
            "--refresh-jpeg",
            help="Force rebuild all JPEG directories (skip check gate).",
        ),
    ] = False,
    refresh_exif_cache: Annotated[
        bool,
        typer.Option(
            "--refresh-exif-cache",
            help="Force re-read all EXIF timestamps.",
        ),
    ] = False,
    redetect_faces: Annotated[
        bool,
        typer.Option(
            "--redetect-faces",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    refresh_face_thumbs: Annotated[
        bool,
        typer.Option(
            "--refresh-face-thumbs",
            help="Refresh face detection thumbnails from originals.",
        ),
    ] = False,
) -> None:
    """Refresh all derived album data for multiple albums."""
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_refresh(
        albums,
        display_base,
        dry_run=dry_run,
        force_browsable=refresh_browsable,
        force_jpeg=refresh_jpeg,
        force_exif_cache=refresh_exif_cache,
        redetect_faces=redetect_faces,
        refresh_face_thumbs=refresh_face_thumbs,
    )
