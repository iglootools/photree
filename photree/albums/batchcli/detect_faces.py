"""``albums detect-faces`` wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ...clihelpers.progress import BatchProgressBar
from ..cmd_handler.detect_faces import batch_detect_faces
from .failures import exit_if_no_albums, exit_with_failures
from .resolution import make_display_fn


def run_batch_detect_faces(
    albums: list[Path],
    display_base: Path | None,
    *,
    redetect: bool = False,
    refresh_thumbs: bool = False,
    dry_run: bool = False,
) -> None:
    """Run face detection on *albums*, print a summary, exit 1 on any failure."""
    cwd = Path.cwd()
    exit_if_no_albums(albums, display_base)

    with BatchProgressBar(
        total=len(albums),
        description="Detecting faces",
        done_description="detect-faces",
    ) as progress:
        result = batch_detect_faces(
            albums,
            redetect=redetect,
            refresh_thumbs=refresh_thumbs,
            dry_run=dry_run,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    verb = "would be processed" if dry_run else "processed"
    typer.echo(
        f"\nDone. {result.succeeded} album(s) {verb}, {len(result.failures)} failed."
    )
    exit_with_failures(result.failures, "detect-faces", cwd)
