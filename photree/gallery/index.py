"""Gallery-specific album indexing — scan a gallery directory."""

from __future__ import annotations

from pathlib import Path

from ..album.store.album_discovery import discover_albums
from ..albums.index import AlbumIndex, build_album_index
from ..fsprotocol import ALBUMS_DIR


def build_album_id_to_path_index(gallery_dir: Path) -> AlbumIndex:
    """Scan all albums under ``<gallery_dir>/albums/`` and build an ID→path index.

    Raises :class:`MissingAlbumIdError` if any discovered album lacks an ID.
    """
    return build_album_index(discover_albums(gallery_dir / ALBUMS_DIR))
