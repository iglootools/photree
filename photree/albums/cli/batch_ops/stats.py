"""``albums stats`` / ``gallery stats`` wrapper."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer
from rich.console import RenderableType

from ....album.naming import parse_album_name
from ....album.stats import models as stats_models
from ....album.stats import output as stats_output
from ....clihelpers.console import console, err_console
from ....clihelpers.progress import BatchProgressBar
from ....common.formatting import indent
from ....common.fs import display_path
from ...cmd_handler.stats import batch_stats
from ..ops import make_display_fn
from .failures import exit_with_failures


def _exit_if_unparseable(
    albums: list[Path], display_base: Path | None, cwd: Path
) -> None:
    unparseable = [a for a in albums if parse_album_name(a.name) is None]
    if unparseable:
        target = (
            f' --dir "{display_path(display_base, cwd)}"'
            if display_base is not None
            else ""
        )
        err_console.print(
            "\n".join(
                [
                    f"{len(unparseable)} album(s) have unparseable names:",
                    *(indent(str(display_path(a, cwd))) for a in unparseable),
                    (
                        f"Run 'photree albums check{target}' to identify and fix "
                        "naming issues."
                    ),
                ]
            ),
            markup=False,
        )
        raise typer.Exit(code=1)


def run_batch_stats(
    albums: list[Path],
    display_base: Path | None,
    *,
    render: Callable[[stats_models.AlbumsStats], RenderableType] | None = None,
) -> None:
    """Shared implementation for gallery stats / albums stats.

    *render* lets the gallery substitute its own report — one that adds the
    collection table — without this module knowing what a gallery is. The
    dependency runs gallery -> albums, never back.
    """
    cwd = Path.cwd()
    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    _exit_if_unparseable(albums, display_base, cwd)
    if display_base is not None:
        typer.echo(f"Found {len(albums)} album(s).\n")

    with BatchProgressBar(
        total=len(albums), description="Computing stats", done_description="stats"
    ) as progress:
        result = batch_stats(
            albums,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    typer.echo("")
    console.print(
        render(result.stats)
        if render is not None
        else stats_output.format_albums_stats(result.stats)
    )
    exit_with_failures(result.failures, "stats", cwd)
