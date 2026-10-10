"""``albums refresh`` / ``gallery refresh`` wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ...clihelpers.progress import BatchProgressBar
from ...foundation.gallery_metadata import resolve_link_mode
from ..cmd_handler.refresh import batch_refresh
from .failures import exit_if_no_albums, exit_with_failures
from .resolution import make_display_fn


def run_batch_refresh(
    albums: list[Path],
    display_base: Path | None,
    *,
    dry_run: bool = False,
    force_browsable: bool = False,
    force_jpeg: bool = False,
    force_exif_cache: bool = False,
    redetect_faces: bool = False,
    refresh_face_thumbs: bool = False,
) -> None:
    """Shared implementation for albums refresh / gallery refresh."""
    cwd = Path.cwd()
    exit_if_no_albums(albums, display_base)

    with BatchProgressBar(
        total=len(albums), description="Refreshing", done_description="refresh"
    ) as progress:
        result = batch_refresh(
            albums,
            link_mode_for=lambda album_dir: resolve_link_mode(None, album_dir),
            dry_run=dry_run,
            force_browsable=force_browsable,
            force_jpeg=force_jpeg,
            force_exif_cache=force_exif_cache,
            redetect_faces=redetect_faces,
            refresh_face_thumbs=refresh_face_thumbs,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    typer.echo(
        f"\nDone. {result.refreshed} album(s) refreshed, {len(result.failures)} failed."
    )
    exit_with_failures(result.failures, "refresh", cwd)
