"""The ``photree albums init`` command."""

import typer

from photree.albums.batchcli.init import run_batch_init
from photree.albums.batchcli.resolution import resolve_init_batch_albums
from photree.albums.cli.app import app
from photree.albums.cli.options import ALBUM_DIR_OPTION, DIR_OPTION
from photree.clihelpers.options import DRY_RUN_OPTION
from photree.clihelpers.runtime import runtime_of


@app.command("init")
def init_cmd(
    ctx: typer.Context,
    base_dir: DIR_OPTION = None,
    album_dirs: ALBUM_DIR_OPTION = None,
    *,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Initialize album metadata (.photree/album.yaml) for multiple albums."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    albums, display_base = resolve_init_batch_albums(base_dir, album_dirs, cwd=cwd)
    run_batch_init(albums, display_base, dry_run=dry_run, cwd=cwd)
