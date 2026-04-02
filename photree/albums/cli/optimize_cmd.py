"""``photree albums optimize`` command."""

from __future__ import annotations

from . import AlbumDirOption, DirOption, albums_app
from ...fs import LinkMode
from ...clihelpers.options import (
    CHECK_BEFORE_OPTION,
    CHECKSUM_OPTION,
    DRY_RUN_OPTION,
    LINK_MODE_REQUIRED_OPTION,
)
from .batch_ops import resolve_batch_albums, run_batch_optimize


@albums_app.command("optimize")
def optimize_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    link_mode: LINK_MODE_REQUIRED_OPTION = LinkMode.HARDLINK,
    check: CHECK_BEFORE_OPTION = True,
    checksum: CHECKSUM_OPTION = True,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Optimize all albums with archives under a directory or from an explicit list."""
    albums, display_base = resolve_batch_albums(base_dir, album_dirs)
    run_batch_optimize(
        albums,
        display_base,
        link_mode=link_mode,
        check=check,
        checksum=checksum,
        dry_run=dry_run,
    )
