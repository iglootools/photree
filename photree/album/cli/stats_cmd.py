from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.runtime import runtime_of
from ...common.fs import display_path
from .. import stats as album_stats
from ..stats import output as stats_output
from . import app
from .media_source_conflict import exit_on_media_source_conflict


@app.command("stats")
def stats_cmd(
    ctx: typer.Context,
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
    cwd = runtime_of(ctx).cwd()
    with exit_on_media_source_conflict(cwd):
        try:
            result = album_stats.compute_album_stats(album_dir)
        except album_stats.UnparseableAlbumNameError as exc:
            err_console.print(
                f'Album name "{exc.album_dir.name}" cannot be parsed.', markup=False
            )
            err_console.print(
                "Run 'photree album check --album-dir "
                f'"{display_path(exc.album_dir, cwd)}"\' to identify naming issues.',
                markup=False,
            )
            raise typer.Exit(code=1) from None

    console.print(stats_output.format_album_stats(result))
