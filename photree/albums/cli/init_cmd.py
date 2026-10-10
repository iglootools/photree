"""``photree albums init`` command."""

from __future__ import annotations

from ...clihelpers.options import DRY_RUN_OPTION
from ..batchcli.init import run_batch_init
from ..batchcli.resolution import resolve_init_batch_albums
from . import AlbumDirOption, DirOption, albums_app


@albums_app.command("init")
def init_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Initialize album metadata (.photree/album.yaml) for multiple albums."""
    albums, display_base = resolve_init_batch_albums(base_dir, album_dirs)
    run_batch_init(albums, display_base, dry_run=dry_run)
