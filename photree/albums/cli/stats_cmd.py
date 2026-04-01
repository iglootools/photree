"""``photree albums stats`` command."""

from __future__ import annotations

from . import AlbumDirOption, DirOption, albums_app
from .batch_ops import resolve_check_batch_albums, run_batch_stats


@albums_app.command("stats")
def stats_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
) -> None:
    """Show aggregated disk usage and content statistics for all albums."""
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_stats(albums, display_base)
