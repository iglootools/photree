"""Media metadata I/O — per-media-source ID mappings.

Each media source gets its own YAML file under ``.photree/media-ids/``:

.. code-block:: text

    .photree/media-ids/
      main.yaml
      bruno.yaml
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from ...fsprotocol import PHOTREE_DIR, _BaseModel
from .protocol import MEDIA_IDS_DIR


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
    """Per-album media metadata — aggregation of all media sources."""

    media_sources: dict[str, MediaSourceMediaMetadata] = Field(
        default_factory=dict,
        description="Media source name -> media ID mappings.",
    )


def _media_ids_dir(album_dir: Path) -> Path:
    return album_dir / PHOTREE_DIR / MEDIA_IDS_DIR


def _source_path(album_dir: Path, source_name: str) -> Path:
    return _media_ids_dir(album_dir) / f"{source_name}.yaml"


def load_media_metadata(album_dir: Path) -> MediaMetadata | None:
    """Read per-source YAML files from ``.photree/media-ids/``."""
    ids_dir = _media_ids_dir(album_dir)
    if not ids_dir.is_dir():
        return None

    sources: dict[str, MediaSourceMediaMetadata] = {}
    for path in sorted(ids_dir.glob("*.yaml")):
        with open(path) as f:
            raw = yaml.safe_load(f)
        if isinstance(raw, dict):
            sources[path.stem] = MediaSourceMediaMetadata.model_validate(raw)

    return MediaMetadata(media_sources=sources) if sources else None


def save_media_metadata(album_dir: Path, metadata: MediaMetadata) -> None:
    """Write per-source YAML files to ``.photree/media-ids/``."""
    ids_dir = _media_ids_dir(album_dir)
    ids_dir.mkdir(parents=True, exist_ok=True)

    # Remove sources that no longer exist
    existing_files = {p.stem for p in ids_dir.glob("*.yaml")}
    for stale in existing_files - set(metadata.media_sources.keys()):
        (ids_dir / f"{stale}.yaml").unlink()

    # Write each source
    for name, source_meta in metadata.media_sources.items():
        _source_path(album_dir, name).write_text(
            yaml.safe_dump(
                source_meta.model_dump(by_alias=True, mode="json"),
                default_flow_style=False,
                sort_keys=False,
            )
        )
