import typer

from ...clihelpers.runtime import runtime_of
from ..batchcli.resolution import resolve_check_batch_albums
from ..batchcli.stats import run_batch_stats
from . import AlbumDirOption, DirOption, app


@app.command("stats")
def stats_cmd(
    ctx: typer.Context,
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
) -> None:
    """Show aggregated disk usage and content statistics for all albums."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs, cwd=cwd)
    run_batch_stats(albums, display_base, cwd=cwd)
