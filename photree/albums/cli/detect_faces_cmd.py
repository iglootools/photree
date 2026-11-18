from typing import Annotated

import typer

from ...clihelpers.options import DRY_RUN_OPTION
from ...clihelpers.runtime import runtime_of
from ...clihelpers.sysdeps import FACE_DETECTION_DEPS, require_system_deps
from ..batchcli.detect_faces import run_batch_detect_faces
from ..batchcli.resolution import resolve_check_batch_albums
from . import AlbumDirOption, DirOption, app


@app.command("detect-faces")
def detect_faces_cmd(
    ctx: typer.Context,
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    dry_run: DRY_RUN_OPTION = False,
    redetect: Annotated[
        bool,
        typer.Option(
            "--redetect",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    refresh_thumbs: Annotated[
        bool,
        typer.Option(
            "--refresh-thumbs",
            help="Refresh face detection thumbnails from originals.",
        ),
    ] = False,
) -> None:
    """Run face detection on images in multiple albums."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    require_system_deps(FACE_DETECTION_DEPS, which=runtime.which)
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs, cwd=cwd)
    run_batch_detect_faces(
        albums,
        display_base,
        redetect=redetect,
        refresh_thumbs=refresh_thumbs,
        dry_run=dry_run,
        cwd=cwd,
        max_workers=runtime.cpu_count(),
    )
