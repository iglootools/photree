"""Media metadata I/O — per-album media ID mappings."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from ...fsprotocol import PHOTREE_DIR, _BaseModel
from .protocol import MEDIA_YAML


class MediaSourceMediaMetadata(_BaseModel):
    """ID mappings for a single media source (images and videos)."""

    images: dict[str, str] = Field(
        default_factory=dict,
        description="UUID -> key (image number for iOS, stem for std).",
    )
    videos: dict[str, str] = Field(
        default_factory=dict,
        description="UUID -> key (image number for iOS, stem for std).",
    )


class MediaMetadata(_BaseModel):
    """Per-album media metadata stored in ``.photree/media.yaml``."""

    media_sources: dict[str, MediaSourceMediaMetadata] = Field(
        default_factory=dict,
        description="Media source name -> media ID mappings.",
    )


def load_media_metadata(album_dir: Path) -> MediaMetadata | None:
    """Read ``.photree/media.yaml``, or ``None`` if missing."""
    path = album_dir / PHOTREE_DIR / MEDIA_YAML
    if not path.is_file():
        return None
    with open(path) as f:
        raw = yaml.safe_load(f)
    return MediaMetadata.model_validate(raw) if isinstance(raw, dict) else None


def save_media_metadata(album_dir: Path, metadata: MediaMetadata) -> None:
    """Write :class:`MediaMetadata` to ``.photree/media.yaml``."""
    photree_dir = album_dir / PHOTREE_DIR
    photree_dir.mkdir(exist_ok=True)
    path = photree_dir / MEDIA_YAML
    path.write_text(
        yaml.safe_dump(
            metadata.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
    )
