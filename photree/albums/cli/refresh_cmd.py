"""``photree albums refresh`` command."""

from __future__ import annotations

from . import AlbumDirOption, DirOption, albums_app
from ...clihelpers.options import DRY_RUN_OPTION
from .batch_ops import resolve_check_batch_albums, run_batch_refresh


@albums_app.command("refresh")
def refresh_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Refresh media metadata (.photree/media.yaml) for multiple albums."""
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_refresh(albums, display_base, dry_run=dry_run)
