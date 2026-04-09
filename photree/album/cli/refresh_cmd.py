"""``photree album refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console
from ...clihelpers.progress import run_with_spinner
from ...common.formatting import CHECK
from ..faces.detect import create_face_analyzer
from ...common.exif import try_start_exiftool
from . import album_app


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
    from ..refresh import refresh_album_derived_data

    exiftool = try_start_exiftool()
    face_analyzer = run_with_spinner(
        "Loading face detection model...", create_face_analyzer
    )

    try:
        run_with_spinner(
            "Refreshing album...",
            lambda: refresh_album_derived_data(
                album_dir,
                exiftool=exiftool,
                face_analyzer=face_analyzer,
                force_browsable=refresh_browsable,
                force_jpeg=refresh_jpeg,
                force_exif_cache=refresh_exif_cache,
                redetect_faces=redetect_faces,
                refresh_face_thumbs=refresh_face_thumbs,
                dry_run=dry_run,
            ),
        )
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)

    console.print(f"{CHECK} album refresh complete")
