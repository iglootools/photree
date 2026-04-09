"""EXIF cache I/O — load/save per-media-source YAML cache files."""

from __future__ import annotations

from pathlib import Path

import yaml

from ...fsprotocol import PHOTREE_DIR
from .protocol import EXIF_CACHE_DIR, ExifCache


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def exif_cache_dir(album_dir: Path) -> Path:
    """Return ``<album>/.photree/exif-cache/``."""
    return album_dir / PHOTREE_DIR / EXIF_CACHE_DIR


def cache_path(album_dir: Path, media_source_name: str) -> Path:
    """Return ``<album>/.photree/exif-cache/{name}.yaml``."""
    return exif_cache_dir(album_dir) / f"{media_source_name}.yaml"


# ---------------------------------------------------------------------------
# YAML I/O
# ---------------------------------------------------------------------------


def load_exif_cache(album_dir: Path, media_source_name: str) -> ExifCache | None:
    """Load EXIF cache from ``.photree/exif-cache/{name}.yaml``."""
    path = cache_path(album_dir, media_source_name)
    if not path.is_file():
        return None
    with open(path) as f:
        raw = yaml.safe_load(f)
    return ExifCache.model_validate(raw) if isinstance(raw, dict) else None


def save_exif_cache(album_dir: Path, media_source_name: str, cache: ExifCache) -> None:
    """Write EXIF cache to ``.photree/exif-cache/{name}.yaml``."""
    path = cache_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            cache.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
    )
