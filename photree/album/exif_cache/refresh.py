"""EXIF cache refresh — scan browsable files, read EXIF for new/changed, save."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...common.exif import exiftool_session, extract_timestamp, get_metadata
from ...common.fs import list_files
from ..exif import TIMESTAMP_TAGS
from ..store.media_source import MediaSource
from ..store.media_sources_discovery import discover_media_sources
from .protocol import EXIF_CACHE_VERSION, ExifCache, ExifCacheEntry
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
    force: bool = False,
    dry_run: bool = False,
) -> ExifCacheRefreshResult:
    """Refresh EXIF timestamp cache for all media sources in an album.

    When *force* is True, re-read all files regardless of mtime.
    *exiftool* can be shared across albums in batch operations; when it is
    ``None`` a transient one is started (and closed) for this album.
    """
    sources = discover_media_sources(album_dir)
    if not sources:
        return ExifCacheRefreshResult(by_media_source=())

    with nullcontext(exiftool) if exiftool is not None else exiftool_session() as et:
        return ExifCacheRefreshResult(
            by_media_source=tuple(
                (
                    ms.name,
                    _refresh_source(
                        album_dir, ms, exiftool=et, force=force, dry_run=dry_run
                    ),
                )
                for ms in sources
            )
        )


# ---------------------------------------------------------------------------
# Per-source refresh
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SourcePlan:
    """What a per-source refresh has to do, computed before any I/O."""

    existing: ExifCache
    current_files: Mapping[str, str]  # cache key -> album-relative path
    keys_to_refresh: tuple[str, ...]
    stale_keys: frozenset[str]

    @property
    def is_noop(self) -> bool:
        return not self.keys_to_refresh and not self.stale_keys


def _load_current_cache(album_dir: Path, ms: MediaSource) -> ExifCache:
    """Load the cache, discarding it when it predates the current layout."""
    cache = load_exif_cache(album_dir, ms.name)
    return cache if cache is not None and cache.is_current else _empty_cache()


def _empty_cache() -> ExifCache:
    return ExifCache(version=EXIF_CACHE_VERSION)


def _plan_source(album_dir: Path, ms: MediaSource, *, force: bool) -> _SourcePlan:
    existing = _load_current_cache(album_dir, ms)
    current_files = _scan_browsable_files(album_dir, ms)
    return _SourcePlan(
        existing=existing,
        current_files=current_files,
        keys_to_refresh=tuple(
            sorted(current_files)
            if force
            else _keys_needing_refresh(current_files, album_dir, existing)
        ),
        stale_keys=frozenset(existing.files) - frozenset(current_files),
    )


def _refresh_source(
    album_dir: Path,
    ms: MediaSource,
    *,
    exiftool: ExifToolHelper | None,
    force: bool,
    dry_run: bool,
) -> ExifCacheSourceResult:
    """Refresh EXIF cache for a single media source."""
    plan = _plan_source(album_dir, ms, force=force)

    if plan.is_noop:
        # Ensure the cache file exists (and is current) even when empty, so the
        # check path knows this source was processed.
        if not dry_run and load_exif_cache(album_dir, ms.name) != plan.existing:
            save_exif_cache(album_dir, ms.name, plan.existing)
        return ExifCacheSourceResult(
            cached=len(plan.current_files), refreshed=0, pruned=0
        )

    if dry_run:
        return ExifCacheSourceResult(
            cached=len(plan.current_files) - len(plan.keys_to_refresh),
            refreshed=len(plan.keys_to_refresh),
            pruned=len(plan.stale_keys),
        )

    return _apply_plan(album_dir, ms, plan, exiftool=exiftool)


def _apply_plan(
    album_dir: Path,
    ms: MediaSource,
    plan: _SourcePlan,
    *,
    exiftool: ExifToolHelper | None,
) -> ExifCacheSourceResult:
    """Read EXIF for new/changed files, merge with the kept entries, and save."""
    new_entries = _read_exif_for_keys(
        plan.keys_to_refresh, plan.current_files, album_dir, exiftool=exiftool
    )
    retained = {
        k: v
        for k, v in plan.existing.files.items()
        if k in plan.current_files and k not in plan.keys_to_refresh
    }
    save_exif_cache(
        album_dir,
        ms.name,
        ExifCache(version=EXIF_CACHE_VERSION, files={**retained, **new_entries}),
    )
    return ExifCacheSourceResult(
        cached=len(retained),
        refreshed=len(new_entries),
        pruned=len(plan.stale_keys),
    )


# ---------------------------------------------------------------------------
# Scanning and diffing
# ---------------------------------------------------------------------------


def cache_key(subdir: str, filename: str) -> str:
    """Return the cache key of a browsable file: ``{subdir}/{stem}``.

    Scoped by directory so that ``main-jpg/clip.jpg`` and ``main-vid/clip.mp4``
    (same stem, different media) do not collide.
    """
    return f"{subdir}/{Path(filename).stem}"


def _scan_browsable_files(album_dir: Path, ms: MediaSource) -> dict[str, str]:
    """Scan browsable directories and return ``{cache_key: relative_path}``.

    Scans ``{name}-jpg/`` and ``{name}-vid/`` (the directories used for
    EXIF date checking).
    """
    return {
        cache_key(subdir, filename): f"{subdir}/{filename}"
        for subdir in (ms.jpg_dir, ms.vid_dir)
        for filename in list_files(album_dir / subdir)
    }


def _keys_needing_refresh(
    current_files: Mapping[str, str],
    album_dir: Path,
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
    return entry is None or (
        file_path.is_file() and entry.mtime != file_path.stat().st_mtime
    )


# ---------------------------------------------------------------------------
# EXIF reading
# ---------------------------------------------------------------------------


def _read_exif_for_keys(
    keys: tuple[str, ...],
    current_files: Mapping[str, str],
    album_dir: Path,
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
            file_name=current_files[key],
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

    metadata_list = get_metadata(files, TIMESTAMP_TAGS, exiftool=exiftool)
    return [extract_timestamp(m, TIMESTAMP_TAGS) for m in metadata_list]
