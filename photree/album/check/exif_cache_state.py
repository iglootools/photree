"""EXIF cache state validation — verify cache presence for album.

During check, the EXIF cache is trusted without per-file mtime
verification. The cache is validated at write time during album refresh.
Use ``--refresh-exif-cache`` on check commands to force a re-read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..exif_cache.protocol import EXIF_CACHE_DIR
from ..exif_cache.store import cache_path
from ..store.protocol import MediaSource
from ...fsprotocol import PHOTREE_DIR


@dataclass(frozen=True)
class ExifCacheStateCheck:
    """Result of EXIF cache state validation for an album."""

    missing_sources: tuple[str, ...]

    @property
    def success(self) -> bool:
        return len(self.missing_sources) == 0

    @property
    def issue_count(self) -> int:
        return len(self.missing_sources)


def check_exif_cache_state(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> ExifCacheStateCheck | None:
    """Validate EXIF cache state for an album.

    Returns ``None`` if no EXIF cache directory exists. Only checks
    that each media source has a cache file — trusts the cache content
    without per-file mtime verification.
    """
    if not media_sources:
        return None

    cache_dir = album_dir / PHOTREE_DIR / EXIF_CACHE_DIR
    if not cache_dir.is_dir():
        return None

    missing = tuple(
        ms.name for ms in media_sources if not cache_path(album_dir, ms.name).is_file()
    )

    return ExifCacheStateCheck(missing_sources=missing) if missing else None
