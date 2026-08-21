"""``albums stats`` / ``gallery stats`` wrapper."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer

from ....album.stats import models as stats_models
from ....album.stats import output as stats_output
from ....clihelpers.console import console, err_console
from ....clihelpers.progress import BatchProgressBar
from ....common.fs import display_path
from ...cmd_handler.stats import batch_stats
from ..ops import make_display_fn


def run_batch_stats(
    albums: list[Path],
    display_base: Path | None,
    *,
    enrich: Callable[[stats_models.GalleryStats], stats_models.GalleryStats]
    | None = None,
) -> None:
    """Shared implementation for gallery stats / albums stats.

    *enrich* lets the gallery add its own totals without this module knowing
    what a gallery is — the dependency runs gallery -> albums, never back.
    """
    from ....album.naming import parse_album_name

    cwd = Path.cwd()

    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    unparseable = [a for a in albums if parse_album_name(a.name) is None]
    if unparseable:
        err_console.print(
            f"{len(unparseable)} album(s) have unparseable names. "
            f"Run photree albums check to identify and fix naming issues:"
        )
        for album_dir in unparseable:
            err_console.print(f"  {display_path(album_dir, cwd)}")
        raise typer.Exit(code=1)

    if display_base is not None:
        typer.echo(f"Found {len(albums)} album(s).\n")

    with BatchProgressBar(
        total=len(albums), description="Computing stats", done_description="stats"
    ) as progress:
        result = batch_stats(
            albums,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success: progress.on_end(name, success=success),
        )

    if enrich is not None:
        result = enrich(result)

    typer.echo("")
    console.print(stats_output.format_gallery_stats(result))
