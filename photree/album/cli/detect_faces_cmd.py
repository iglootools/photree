"""``photree album detect-faces`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..faces.refresh import refresh_face_data
from . import album_app


@album_app.command("detect-faces")
def detect_faces_cmd(
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
    redetect: Annotated[
        bool,
        typer.Option(
            "--redetect",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    regenerate_thumbs: Annotated[
        bool,
        typer.Option(
            "--regenerate-thumbs",
            help="Regenerate face detection thumbnails from originals.",
        ),
    ] = False,
) -> None:
    """Run face detection on album images."""
    result = refresh_face_data(
        album_dir,
        redetect=redetect,
        regenerate_thumbs=regenerate_thumbs,
        dry_run=dry_run,
    )

    if not result.by_media_source:
        typer.echo("No media sources with archives found.")
        raise typer.Exit(code=0)

    for ms_name, ms_result in result.by_media_source:
        parts = [
            f"{ms_result.processed} processed",
            f"{ms_result.skipped} skipped",
        ]
        if ms_result.faces_detected:
            parts.append(f"{ms_result.faces_detected} face(s)")
        if ms_result.failed:
            parts.append(f"{ms_result.failed} failed")
        typer.echo(f"  {ms_name}: {', '.join(parts)}")
