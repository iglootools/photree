"""Index the gallery's albums by ID."""

from pathlib import Path

from photree.album.store.album_discovery import discover_albums
from photree.albums.index import AlbumIndex, build_album_index
from photree.foundation.layout import ALBUMS_DIR


def build_album_id_to_path_index(gallery_dir: Path) -> AlbumIndex:
    """
    Scan all albums under ``<gallery_dir>/albums/`` and build an ID→path index.

    Raises :class:`MissingAlbumIdError` if any discovered album lacks an ID.
    """
    return build_album_index(discover_albums(gallery_dir / ALBUMS_DIR))
