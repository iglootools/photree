"""``photree album detect-faces`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import err_console
from ...clihelpers.sysdeps import FACE_DETECTION_DEPS, require_system_deps
from ...common.formatting import indent
from ..faces.detect import memoized_face_analyzer_factory
from ..faces.refresh import (
    FaceSourceRefreshResult,
    format_face_failures,
    refresh_face_data,
)
from . import album_app
from .helpers import exit_on_media_source_conflict


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
    refresh_thumbs: Annotated[
        bool,
        typer.Option(
            "--refresh-thumbs",
            help="Refresh face detection thumbnails from originals.",
        ),
    ] = False,
) -> None:
    """Run face detection on album images."""
    require_system_deps(FACE_DETECTION_DEPS)

    with exit_on_media_source_conflict(Path.cwd()):
        result = refresh_face_data(
            album_dir,
            analyzer_factory=memoized_face_analyzer_factory(),
            redetect=redetect,
            refresh_thumbs=refresh_thumbs,
            dry_run=dry_run,
        )

    if not result.by_media_source:
        typer.echo("No media sources with archives found.")
        raise typer.Exit(code=0)

    for ms_name, ms_result in result.by_media_source:
        typer.echo(indent(f"{ms_name}: {_source_summary(ms_result)}"))

    if result.failures:
        err_console.print("\nFailed images:")
        for line in format_face_failures(result.failures):
            err_console.print(indent(line), markup=False)
        raise typer.Exit(code=1)


def _source_summary(ms_result: FaceSourceRefreshResult) -> str:
    return ", ".join(
        [
            f"{ms_result.processed} processed",
            f"{ms_result.skipped} skipped",
            *(
                [f"{ms_result.faces_detected} face(s)"]
                if ms_result.faces_detected
                else []
            ),
            *([f"{ms_result.failed} failed"] if ms_result.failed else []),
        ]
    )
