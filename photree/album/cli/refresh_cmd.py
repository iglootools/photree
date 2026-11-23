"""The ``photree album refresh`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.check.output import derived_failures_report
from photree.album.cli.app import app
from photree.album.cli.media_source_conflict import exit_on_media_source_conflict
from photree.album.faces.detect import memoized_face_analyzer_factory
from photree.album.refresh import AlbumRefreshResult, refresh_album_derived_data
from photree.clihelpers.console import console, err_console
from photree.clihelpers.options import DRY_RUN_OPTION
from photree.clihelpers.progress import run_with_spinner
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.sysdeps import refresh_deps, require_system_deps
from photree.common.exif import exiftool_session
from photree.common.formatting import CHECK, format_dry_run
from photree.common.fs import display_path
from photree.foundation.gallery_metadata import resolve_link_mode


@app.command("refresh")
def refresh_cmd(
    ctx: typer.Context,
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path(),
    *,
    dry_run: DRY_RUN_OPTION = False,
    refresh_browsable: Annotated[
        bool,
        typer.Option(
            "--refresh-browsable",
            help="Force rebuild all browsable dirs and JPEGs (skip check gate).",
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
    """Refresh derived album data (browsable, JPEG, media IDs, EXIF cache, faces)."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    which = runtime.which
    require_system_deps(refresh_deps(), which=which)

    with exiftool_session(which=which) as exiftool, exit_on_media_source_conflict(cwd):
        result = run_with_spinner(
            "Refreshing album...",
            lambda: refresh_album_derived_data(
                album_dir,
                link_mode=resolve_link_mode(None, album_dir),
                exiftool=exiftool,
                analyzer_factory=memoized_face_analyzer_factory(),
                force_browsable=refresh_browsable,
                force_jpeg=refresh_jpeg,
                force_exif_cache=refresh_exif_cache,
                redetect_faces=redetect_faces,
                refresh_face_thumbs=refresh_face_thumbs,
                dry_run=dry_run,
                max_workers=runtime.cpu_count(),
            ),
        )

    if not result.success:
        _report_failures(result, album_dir=display_path(album_dir, cwd))
        raise typer.Exit(code=1)

    console.print(
        format_dry_run(
            f"{CHECK} album refresh {'planned' if dry_run else 'complete'}",
            dry_run=dry_run,
            markup=True,
        ),
    )


def _report_failures(result: AlbumRefreshResult, *, album_dir: Path) -> None:
    """Print every JPEG and face-detection failure, each with its retry command."""
    err_console.print(
        derived_failures_report(
            result.jpeg_failures,
            result.face_failures,
            str(album_dir),
        ),
    )
