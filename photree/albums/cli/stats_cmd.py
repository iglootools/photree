"""The ``photree albums stats`` command."""

import typer

from photree.albums.batchcli.resolution import resolve_check_batch_albums
from photree.albums.batchcli.stats import run_batch_stats
from photree.albums.cli.app import app
from photree.albums.cli.options import ALBUM_DIR_OPTION, DIR_OPTION
from photree.clihelpers.runtime import runtime_of


@app.command("stats")
def stats_cmd(
    ctx: typer.Context,
    base_dir: DIR_OPTION = None,
    album_dirs: ALBUM_DIR_OPTION = None,
) -> None:
    """Show aggregated disk usage and content statistics for all albums."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs, cwd=cwd)
    run_batch_stats(albums, display_base, cwd=cwd)
