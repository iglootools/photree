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
    """Refresh media metadata and face detection data for multiple albums."""
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_refresh(
        albums,
        display_base,
        dry_run=dry_run,
        redetect_faces=redetect_faces,
        refresh_face_thumbs=refresh_face_thumbs,
    )
