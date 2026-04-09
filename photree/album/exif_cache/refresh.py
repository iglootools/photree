"""EXIF cache refresh — scan browsable files, read EXIF for new/changed, save."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...common.exif import try_start_exiftool
from ...common.fs import list_files
from ..exif import _TIMESTAMP_TAGS
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import MediaSource
from .protocol import ExifCache, ExifCacheEntry
from .store import load_exif_cache, save_exif_cache


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExifCacheSourceResult:
    """Result of refreshing EXIF cache for a single media source."""

    cached: int
    refreshed: int
    pruned: int

    @property
    def changed(self) -> bool:
        return self.refreshed > 0 or self.pruned > 0


@dataclass(frozen=True)
class ExifCacheRefreshResult:
    """Result of refreshing EXIF cache for an album."""

    by_media_source: tuple[tuple[str, ExifCacheSourceResult], ...]

    @property
    def total_refreshed(self) -> int:
        return sum(r.refreshed for _, r in self.by_media_source)

    @property
    def changed(self) -> bool:
        return any(r.changed for _, r in self.by_media_source)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def refresh_exif_cache(
    album_dir: Path,
    *,
    exiftool: ExifToolHelper | None = None,
    dry_run: bool = False,
) -> ExifCacheRefreshResult:
    """Refresh EXIF timestamp cache for all media sources in an album.

    *exiftool* can be shared across albums in batch operations.
    """
    sources = discover_media_sources(album_dir)
    if not sources:
        return ExifCacheRefreshResult(by_media_source=())

    # Reuse caller's exiftool or start a transient one
    owns_exiftool = exiftool is None
    et = exiftool or try_start_exiftool()

    try:
        results = [
            (
                ms.name,
                _refresh_source(album_dir, ms, exiftool=et, dry_run=dry_run),
            )
            for ms in sources
        ]
    finally:
        if owns_exiftool and et is not None:
            et.__exit__(None, None, None)

    return ExifCacheRefreshResult(by_media_source=tuple(results))


# ---------------------------------------------------------------------------
# Per-source refresh
# ---------------------------------------------------------------------------


def _refresh_source(
    album_dir: Path,
    ms: MediaSource,
    *,
    exiftool: ExifToolHelper | None,
    dry_run: bool,
) -> ExifCacheSourceResult:
    """Refresh EXIF cache for a single media source."""
    existing = load_exif_cache(album_dir, ms.name) or ExifCache()

    current_files = _scan_browsable_files(album_dir, ms)
    current_keys = set(current_files.keys())
    stale_keys = set(existing.files.keys()) - current_keys

    keys_to_refresh = _keys_needing_refresh(current_files, album_dir, ms, existing)

    if not keys_to_refresh and not stale_keys:
        # Ensure cache file exists even when empty (no browsable files),
        # so the check path knows this source was processed.
        if not dry_run and load_exif_cache(album_dir, ms.name) is None:
            save_exif_cache(album_dir, ms.name, existing)
        return ExifCacheSourceResult(cached=len(current_keys), refreshed=0, pruned=0)

    if dry_run:
        return ExifCacheSourceResult(
            cached=len(current_keys) - len(keys_to_refresh),
            refreshed=len(keys_to_refresh),
            pruned=len(stale_keys),
        )

    # Read EXIF for new/changed files
    new_entries = _read_exif_for_keys(
        keys_to_refresh, current_files, album_dir, ms, exiftool=exiftool
    )

    # Merge: keep unchanged, add/replace refreshed, drop stale
    retained = {
        k: v
        for k, v in existing.files.items()
        if k in current_keys and k not in keys_to_refresh
    }
    updated = ExifCache(files={**retained, **new_entries})

    save_exif_cache(album_dir, ms.name, updated)

    return ExifCacheSourceResult(
        cached=len(retained),
        refreshed=len(new_entries),
        pruned=len(stale_keys),
    )


# ---------------------------------------------------------------------------
# Scanning and diffing
# ---------------------------------------------------------------------------


def _scan_browsable_files(album_dir: Path, ms: MediaSource) -> dict[str, str]:
    """Scan browsable directories and return ``{key: filename}`` mapping.

    Scans ``{name}-jpg/`` and ``{name}-vid/`` (the directories used for
    EXIF date checking).
    """
    result: dict[str, str] = {}
    for subdir in (ms.jpg_dir, ms.vid_dir):
        dir_path = album_dir / subdir
        if dir_path.is_dir():
            for filename in list_files(dir_path):
                key = Path(filename).stem
                result[key] = f"{subdir}/{filename}"
    return result


def _keys_needing_refresh(
    current_files: dict[str, str],
    album_dir: Path,
    ms: MediaSource,
    cache: ExifCache,
) -> list[str]:
    """Return keys whose EXIF timestamps need re-reading."""
    return sorted(
        key
        for key, rel_path in current_files.items()
        if _needs_refresh(key, album_dir / rel_path, cache)
    )


def _needs_refresh(key: str, file_path: Path, cache: ExifCache) -> bool:
    """Return True when a file's EXIF timestamp needs re-reading."""
    entry = cache.files.get(key)
    if entry is None:
        return True
    return file_path.is_file() and entry.mtime != file_path.stat().st_mtime


# ---------------------------------------------------------------------------
# EXIF reading
# ---------------------------------------------------------------------------


def _read_exif_for_keys(
    keys: list[str],
    current_files: dict[str, str],
    album_dir: Path,
    ms: MediaSource,
    *,
    exiftool: ExifToolHelper | None,
) -> dict[str, ExifCacheEntry]:
    """Batch-read EXIF timestamps for a set of keys."""
    files = [album_dir / current_files[key] for key in keys]

    # Batch read via exiftool
    timestamps = _batch_read_timestamps(files, exiftool=exiftool)

    return {
        key: ExifCacheEntry(
            mtime=(album_dir / current_files[key]).stat().st_mtime,
            file_name=Path(current_files[key]).name,
            timestamp=ts.isoformat() if ts is not None else None,
        )
        for key, ts in zip(keys, timestamps)
    }


def _batch_read_timestamps(
    files: list[Path],
    *,
    exiftool: ExifToolHelper | None,
) -> list[datetime | None]:
    """Read EXIF timestamps for files, returning None for unreadable ones."""
    if not files:
        return []

    from ...common.exif import extract_timestamp, get_metadata

    metadata_list = get_metadata(files, _TIMESTAMP_TAGS, exiftool=exiftool)
    return [extract_timestamp(m, _TIMESTAMP_TAGS) for m in metadata_list]
