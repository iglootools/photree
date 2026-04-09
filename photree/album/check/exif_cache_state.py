"""EXIF cache state validation — verify cache consistency with album contents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..exif_cache.protocol import EXIF_CACHE_DIR
from ..exif_cache.store import cache_path, load_exif_cache
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import MediaSource
from ...common.fs import list_files
from ...fsprotocol import PHOTREE_DIR


@dataclass(frozen=True)
class ExifCacheStateCheck:
    """Result of EXIF cache state validation for an album."""

    uncached: tuple[str, ...]
    stale_entries: tuple[str, ...]
    stale_mtimes: tuple[str, ...]

    @property
    def success(self) -> bool:
        return (
            len(self.uncached) == 0
            and len(self.stale_entries) == 0
            and len(self.stale_mtimes) == 0
        )

    @property
    def issue_count(self) -> int:
        return len(self.uncached) + len(self.stale_entries) + len(self.stale_mtimes)


def check_exif_cache_state(album_dir: Path) -> ExifCacheStateCheck | None:
    """Validate EXIF cache state for an album.

    Returns ``None`` if no EXIF cache exists.
    """
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        return None

    cache_dir = album_dir / PHOTREE_DIR / EXIF_CACHE_DIR
    if not cache_dir.is_dir():
        return None

    has_any_cache = any(
        cache_path(album_dir, ms.name).is_file() for ms in media_sources
    )
    if not has_any_cache:
        return None

    per_source = [_check_source(album_dir, ms) for ms in media_sources]

    return ExifCacheStateCheck(
        uncached=tuple(s for r in per_source for s in r.uncached),
        stale_entries=tuple(s for r in per_source for s in r.stale_entries),
        stale_mtimes=tuple(s for r in per_source for s in r.stale_mtimes),
    )


# ---------------------------------------------------------------------------
# Per-source check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SourceCheck:
    uncached: tuple[str, ...]
    stale_entries: tuple[str, ...]
    stale_mtimes: tuple[str, ...]


_EMPTY = _SourceCheck(uncached=(), stale_entries=(), stale_mtimes=())


def _check_source(album_dir: Path, ms: MediaSource) -> _SourceCheck:
    """Validate EXIF cache for a single media source."""
    cache = load_exif_cache(album_dir, ms.name)
    if cache is None:
        return _EMPTY

    current_keys = _scan_browsable_keys(album_dir, ms)
    cached_keys = set(cache.files.keys())

    return _SourceCheck(
        uncached=tuple(f"{ms.name}:{k}" for k in sorted(current_keys - cached_keys)),
        stale_entries=tuple(
            f"{ms.name}:{k}" for k in sorted(cached_keys - current_keys)
        ),
        stale_mtimes=tuple(
            f"{ms.name}:{key}"
            for key, entry in cache.files.items()
            if key in current_keys
            and _is_mtime_stale(album_dir, ms, entry.file_name, entry.mtime)
        ),
    )


def _scan_browsable_keys(album_dir: Path, ms: MediaSource) -> set[str]:
    """Return the set of media keys in browsable directories."""
    return {
        Path(f).stem
        for subdir in (ms.jpg_dir, ms.vid_dir)
        if (album_dir / subdir).is_dir()
        for f in list_files(album_dir / subdir)
    }


def _is_mtime_stale(
    album_dir: Path, ms: MediaSource, file_name: str, cached_mtime: float
) -> bool:
    """Return True when a browsable file's mtime differs from the cached value."""
    for subdir in (ms.jpg_dir, ms.vid_dir):
        candidate = album_dir / subdir / file_name
        if candidate.is_file():
            return candidate.stat().st_mtime != cached_mtime
    return False
