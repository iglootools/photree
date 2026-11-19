from pathlib import Path
from typing import Annotated

import typer

from ...albums.batchcli.resolution import resolve_check_batch_albums
from ...albums.batchcli.stats import run_batch_stats
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...clihelpers.runtime import runtime_of
from ..stats import compute_gallery_stats, format_gallery_stats
from . import app


@app.command("stats")
def stats_cmd(
    ctx: typer.Context,
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Show aggregated disk usage and content statistics for all albums in the gallery."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    resolved = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    albums, display_base = resolve_check_batch_albums(resolved, None, cwd=cwd)
    run_batch_stats(
        albums,
        display_base,
        render=lambda albums_stats: format_gallery_stats(
            compute_gallery_stats(albums_stats, resolved)
        ),
        cwd=cwd,
    )
