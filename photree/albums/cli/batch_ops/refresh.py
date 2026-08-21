"""``albums refresh`` / ``gallery refresh`` wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ....clihelpers.console import err_console
from ....clihelpers.progress import BatchProgressBar
from ....common.fs import display_path
from ...cmd_handler.refresh import batch_refresh
from ..ops import make_display_fn
from .failures import batch_failures_report


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

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")

    with BatchProgressBar(
        total=len(albums), description="Refreshing", done_description="refresh"
    ) as progress:
        result = batch_refresh(
            albums,
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
        f"\nDone. {result.refreshed} album(s) refreshed,"
        f" {len(result.failed_albums)} failed."
    )

    if result.failed_albums:
        err_console.print(batch_failures_report(result.failures, cwd))
        err_console.print("\nTo investigate failures:")
        for album_dir in result.failed_albums:
            err_console.print(
                f'  photree album refresh --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)
