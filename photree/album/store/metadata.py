"""Album metadata I/O."""

from __future__ import annotations

from pathlib import Path

import yaml

from ...fsprotocol import PHOTREE_DIR
from .protocol import ALBUM_YAML, AlbumMetadata


def load_album_metadata(album_dir: Path) -> AlbumMetadata | None:
    """Read ``.photree/album.yaml``, or ``None`` if missing."""
    path = album_dir / PHOTREE_DIR / ALBUM_YAML
    if not path.is_file():
        return None
    with open(path) as f:
        raw = yaml.safe_load(f)
    return AlbumMetadata.model_validate(raw) if isinstance(raw, dict) else None


def save_album_metadata(album_dir: Path, metadata: AlbumMetadata) -> None:
    """Write :class:`AlbumMetadata` to ``.photree/album.yaml``."""
    photree_dir = album_dir / PHOTREE_DIR
    photree_dir.mkdir(exist_ok=True)
    path = photree_dir / ALBUM_YAML
    path.write_text(
        yaml.safe_dump(
            metadata.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
    )
