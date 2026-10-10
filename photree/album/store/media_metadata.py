"""Media metadata I/O — per-media-source ID mappings.

Each media source gets its own YAML file under ``.photree/media-ids/``:

.. code-block:: text

    .photree/media-ids/
      main.yaml
      bruno.yaml
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from ...fsprotocol import (
    PHOTREE_DIR,
    InvalidMetadataError,
    PhotreeModel,
    load_yaml_mapping,
    validate_metadata,
    write_yaml,
)
from .protocol import MEDIA_IDS_DIR


class MediaSourceMediaMetadata(PhotreeModel):
    """ID mappings for a single media source (images and videos)."""

    images: dict[str, str] = Field(
        default_factory=dict,
        description="UUID -> key (image number for iOS, stem for std).",
    )
    videos: dict[str, str] = Field(
        default_factory=dict,
        description="UUID -> key (image number for iOS, stem for std).",
    )


class MediaMetadata(PhotreeModel):
    """Per-album media metadata — aggregation of all media sources."""

    media_sources: dict[str, MediaSourceMediaMetadata] = Field(
        default_factory=dict,
        description="Media source name -> media ID mappings.",
    )


def _media_ids_dir(album_dir: Path) -> Path:
    return album_dir / PHOTREE_DIR / MEDIA_IDS_DIR


def _source_path(album_dir: Path, source_name: str) -> Path:
    return _media_ids_dir(album_dir) / f"{source_name}.yaml"


def _load_source_file(path: Path) -> MediaSourceMediaMetadata:
    """Read one ``media-ids/{name}.yaml`` file that is known to exist."""
    raw = load_yaml_mapping(path)
    if raw is None:
        # Only reachable if the file vanished between the glob and the read.
        raise InvalidMetadataError(path, "file disappeared while reading")
    return validate_metadata(path, MediaSourceMediaMetadata, raw)


def load_media_metadata(album_dir: Path) -> MediaMetadata | None:
    """Read per-source YAML files from ``.photree/media-ids/``.

    Returns ``None`` when there is no media-ids file at all. A file that is
    present but unreadable raises
    :class:`~photree.fsprotocol.InvalidMetadataError` rather than being
    skipped: dropping it would make the next refresh mint fresh UUIDs for every
    media item of that source, breaking collection references.
    """
    ids_dir = _media_ids_dir(album_dir)
    sources = (
        {path.stem: _load_source_file(path) for path in sorted(ids_dir.glob("*.yaml"))}
        if ids_dir.is_dir()
        else {}
    )
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
        write_yaml(
            _source_path(album_dir, name),
            source_meta.model_dump(by_alias=True, mode="json"),
        )
