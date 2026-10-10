"""EXIF cache I/O — load/save per-media-source YAML cache files."""

from __future__ import annotations

from pathlib import Path

from ...foundation.layout import PHOTREE_DIR
from ...foundation.metadata_io import load_yaml_mapping, validate_metadata, write_yaml
from .protocol import EXIF_CACHE_DIR, ExifCache

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def exif_cache_dir(album_dir: Path) -> Path:
    """Return ``<album>/.photree/cache/exif/``."""
    return album_dir / PHOTREE_DIR / EXIF_CACHE_DIR


def cache_path(album_dir: Path, media_source_name: str) -> Path:
    """Return ``<album>/.photree/cache/exif/{name}.yaml``."""
    return exif_cache_dir(album_dir) / f"{media_source_name}.yaml"


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------


def load_exif_cache(album_dir: Path, media_source_name: str) -> ExifCache | None:
    """Load EXIF cache from ``.photree/cache/exif/{name}.yaml``.

    Returns ``None`` when the file is absent. A present-but-corrupt file
    raises :class:`~photree.foundation.metadata_io.InvalidMetadataError`; the cache is
    derived data, so the fix is ``album refresh --refresh-exif-cache`` or
    deleting the file — not silently reading around it.
    """
    path = cache_path(album_dir, media_source_name)
    raw = load_yaml_mapping(path)
    return validate_metadata(path, ExifCache, raw) if raw is not None else None


def save_exif_cache(album_dir: Path, media_source_name: str, cache: ExifCache) -> None:
    """Write EXIF cache to ``.photree/cache/exif/{name}.yaml``."""
    path = cache_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(path, cache.model_dump(by_alias=True, mode="json"))
