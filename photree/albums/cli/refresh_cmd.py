from typing import Annotated

import typer

from ...clihelpers.options import DRY_RUN_OPTION
from ...clihelpers.runtime import runtime_of
from ...clihelpers.sysdeps import refresh_deps, require_system_deps
from ..batchcli.refresh import run_batch_refresh
from ..batchcli.resolution import resolve_check_batch_albums
from . import ALBUM_DIR_OPTION, DIR_OPTION, app


@app.command("refresh")
def refresh_cmd(
    ctx: typer.Context,
    base_dir: DIR_OPTION = None,
    album_dirs: ALBUM_DIR_OPTION = None,
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
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    which = runtime.which
    require_system_deps(refresh_deps(), which=which)

    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs, cwd=cwd)
    run_batch_refresh(
        albums,
        display_base,
        dry_run=dry_run,
        force_browsable=refresh_browsable,
        force_jpeg=refresh_jpeg,
        force_exif_cache=refresh_exif_cache,
        redetect_faces=redetect_faces,
        refresh_face_thumbs=refresh_face_thumbs,
        runtime=runtime,
    )
