"""``photree album refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.progress import run_with_spinner
from ...clihelpers.sysdeps import refresh_deps, require_system_deps
from ...common.exif import exiftool_session
from ...common.formatting import CHECK
from ...common.fs import display_path
from ..check.output import derived_failures_report
from ..faces.detect import memoized_face_analyzer_factory
from ..refresh import AlbumRefreshResult, refresh_album_derived_data
from . import album_app
from .helpers import exit_on_media_source_conflict


@album_app.command("refresh")
def refresh_cmd(
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
    ] = Path("."),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would change without writing."),
    ] = False,
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
    """Refresh all derived album data (browsable, JPEG, media IDs, EXIF cache, faces)."""
    require_system_deps(refresh_deps())

    cwd = Path.cwd()
    with exiftool_session() as exiftool, exit_on_media_source_conflict(cwd):
        result = run_with_spinner(
            "Refreshing album...",
            lambda: refresh_album_derived_data(
                album_dir,
                exiftool=exiftool,
                analyzer_factory=memoized_face_analyzer_factory(),
                force_browsable=refresh_browsable,
                force_jpeg=refresh_jpeg,
                force_exif_cache=refresh_exif_cache,
                redetect_faces=redetect_faces,
                refresh_face_thumbs=refresh_face_thumbs,
                dry_run=dry_run,
            ),
        )

    if not result.success:
        _report_failures(result, album_dir=display_path(album_dir, cwd))
        raise typer.Exit(code=1)

    console.print(f"{CHECK} album refresh complete")


def _report_failures(result: AlbumRefreshResult, *, album_dir: Path) -> None:
    """Print every JPEG and face-detection failure, each with its retry command."""
    err_console.print(
        derived_failures_report(
            result.jpeg_failures, result.face_failures, str(album_dir)
        )
    )
