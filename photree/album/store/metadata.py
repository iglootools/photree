"""Reading and writing an album's ``.photree/album.yaml``."""

from pathlib import Path

from photree.album.store.protocol import ALBUM_YAML, AlbumMetadata
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.metadata_io import (
    load_yaml_mapping,
    validate_metadata,
    write_yaml,
)


def album_metadata_path(album_dir: Path) -> Path:
    """Return the path of the album's ``.photree/album.yaml``."""
    return album_dir / PHOTREE_DIR / ALBUM_YAML


def load_album_metadata(album_dir: Path) -> AlbumMetadata | None:
    """
    Read ``.photree/album.yaml``, or ``None`` if missing.

    Raises :class:`~photree.foundation.metadata_io.InvalidMetadataError` when the file
    exists but cannot be read: treating a corrupt file as absent is how
    ``album init`` / ``album fix --id`` would mint a new ID over the old one.
    """
    path = album_metadata_path(album_dir)
    raw = load_yaml_mapping(path)
    return validate_metadata(path, AlbumMetadata, raw) if raw is not None else None


def save_album_metadata(album_dir: Path, metadata: AlbumMetadata) -> None:
    """
    Write *metadata* to the album's ``.photree/album.yaml``.

    Creates ``.photree/`` when missing; *album_dir* must exist.
    """
    path = album_metadata_path(album_dir)
    path.parent.mkdir(exist_ok=True)
    write_yaml(path, metadata.model_dump(by_alias=True, mode="json"))
