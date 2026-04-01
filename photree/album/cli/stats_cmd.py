"""``photree album stats`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import album_app
from .. import stats as album_stats
from ..stats import output as stats_output
from ...clicommons.console import console, err_console


@album_app.command("stats")
def stats_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to analyze.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """Show disk usage and content statistics for a single album."""
    try:
        result = album_stats.compute_album_stats(album_dir)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from None

    console.print(stats_output.format_album_stats(result))
