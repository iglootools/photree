"""Album metadata I/O."""

from __future__ import annotations

from pathlib import Path

from ...fsprotocol import PHOTREE_DIR, load_yaml_mapping, validate_metadata, write_yaml
from .protocol import ALBUM_YAML, AlbumMetadata


def album_metadata_path(album_dir: Path) -> Path:
    """Return ``<album>/.photree/album.yaml``."""
    return album_dir / PHOTREE_DIR / ALBUM_YAML


def load_album_metadata(album_dir: Path) -> AlbumMetadata | None:
    """Read ``.photree/album.yaml``, or ``None`` if missing.

    Raises :class:`~photree.fsprotocol.InvalidMetadataError` when the file
    exists but cannot be read: treating a corrupt file as absent is how
    ``album init`` / ``album fix --id`` would mint a new ID over the old one.
    """
    path = album_metadata_path(album_dir)
    raw = load_yaml_mapping(path)
    return validate_metadata(path, AlbumMetadata, raw) if raw is not None else None


def save_album_metadata(album_dir: Path, metadata: AlbumMetadata) -> None:
    """Write :class:`AlbumMetadata` to ``.photree/album.yaml``."""
    path = album_metadata_path(album_dir)
    path.parent.mkdir(exist_ok=True)
    write_yaml(path, metadata.model_dump(by_alias=True, mode="json"))
