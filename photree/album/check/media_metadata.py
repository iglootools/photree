"""Media metadata check — verify media-ids is in sync with directory structure."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...common.fs import list_files
from ..store.media_metadata import (
    MediaSourceMediaMetadata,
    load_media_metadata,
)
from ..store.media_sources import dedup_media_dict
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import (
    IMG_EXTENSIONS,
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    MediaSource,
    VID_EXTENSIONS,
    _KeyFn,
)


# ---------------------------------------------------------------------------
# Intermediate types
# ---------------------------------------------------------------------------


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True)
class UnmatchedKey:
    """A media key present on disk but not in media-ids, or vice versa."""

    media_source: str
    media_type: MediaType
    key: str


@dataclass(frozen=True)
class DuplicateId:
    """A media UUID that appears more than once within the album."""

    uuid: str
    count: int


# ---------------------------------------------------------------------------
# Check result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MediaMetadataCheck:
    """Result of checking media metadata against the directory structure."""

    has_media_metadata: bool
    image_count: int = 0
    video_count: int = 0
    new_keys: tuple[UnmatchedKey, ...] = ()
    """Keys on disk but not in media-ids."""
    stale_keys: tuple[UnmatchedKey, ...] = ()
    """Keys in media-ids but not on disk."""
    duplicate_ids: tuple[DuplicateId, ...] = ()
    """UUIDs that appear more than once within the album."""

    @property
    def in_sync(self) -> bool:
        return (
            self.has_media_metadata
            and not self.new_keys
            and not self.stale_keys
            and not self.duplicate_ids
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_keys(
    album_dir: Path,
    directory: str,
    extensions: frozenset[str],
    key_fn: _KeyFn,
) -> set[str]:
    """Scan a directory and return the set of deduped media keys."""
    return set(
        dedup_media_dict(list_files(album_dir / directory), extensions, key_fn).keys()
    )


def _diff_keys(
    existing_keys: set[str],
    disk_keys: set[str],
    ms_name: str,
    media_type: MediaType,
) -> tuple[tuple[UnmatchedKey, ...], tuple[UnmatchedKey, ...]]:
    """Compute new and stale keys for a single media type.

    Returns ``(new_entries, stale_entries)`` as sorted tuples.
    """
    new = tuple(
        UnmatchedKey(ms_name, media_type, k) for k in sorted(disk_keys - existing_keys)
    )
    stale = tuple(
        UnmatchedKey(ms_name, media_type, k) for k in sorted(existing_keys - disk_keys)
    )
    return new, stale


@dataclass(frozen=True)
class _SourceCheckResult:
    new: tuple[UnmatchedKey, ...]
    stale: tuple[UnmatchedKey, ...]
    uuids: tuple[str, ...]
    image_count: int
    video_count: int


def _check_media_source(
    album_dir: Path,
    ms: MediaSource,
    existing_ms: MediaSourceMediaMetadata,
) -> _SourceCheckResult:
    """Check a single media source against its on-disk files."""
    img_ext = IOS_IMG_EXTENSIONS if ms.is_ios else IMG_EXTENSIONS
    vid_ext = IOS_VID_EXTENSIONS if ms.is_ios else VID_EXTENSIONS

    img_new, img_stale = _diff_keys(
        set(existing_ms.images.values()),
        _scan_keys(album_dir, ms.orig_img_dir, img_ext, ms.key_fn),
        ms.name,
        MediaType.IMAGE,
    )
    vid_new, vid_stale = _diff_keys(
        set(existing_ms.videos.values()),
        _scan_keys(album_dir, ms.orig_vid_dir, vid_ext, ms.key_fn),
        ms.name,
        MediaType.VIDEO,
    )

    return _SourceCheckResult(
        new=(*img_new, *vid_new),
        stale=(*img_stale, *vid_stale),
        uuids=(*existing_ms.images.keys(), *existing_ms.videos.keys()),
        image_count=len(existing_ms.images),
        video_count=len(existing_ms.videos),
    )


def _stale_source_result(
    ms_name: str, ms_meta: MediaSourceMediaMetadata
) -> _SourceCheckResult:
    """Build a check result for a media source that no longer exists on disk."""
    return _SourceCheckResult(
        new=(),
        stale=tuple(
            [
                *(
                    UnmatchedKey(ms_name, MediaType.IMAGE, k)
                    for k in sorted(ms_meta.images.values())
                ),
                *(
                    UnmatchedKey(ms_name, MediaType.VIDEO, k)
                    for k in sorted(ms_meta.videos.values())
                ),
            ]
        ),
        uuids=(*ms_meta.images.keys(), *ms_meta.videos.keys()),
        image_count=len(ms_meta.images),
        video_count=len(ms_meta.videos),
    )


def _find_duplicate_ids(uuids: list[str]) -> tuple[DuplicateId, ...]:
    """Detect UUIDs that appear more than once."""
    counts = Counter(uuids)
    return tuple(
        DuplicateId(uuid=uuid, count=count)
        for uuid, count in sorted(counts.items())
        if count > 1
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_media_metadata(album_dir: Path) -> MediaMetadataCheck:
    """Compare ``.photree/media-ids`` against actual files on disk."""
    metadata = load_media_metadata(album_dir)
    if metadata is None:
        return MediaMetadataCheck(has_media_metadata=False)

    media_sources = discover_media_sources(album_dir)
    discovered_names = {ms.name for ms in media_sources}

    # Check discovered media sources against metadata
    source_results = [
        _check_media_source(
            album_dir,
            ms,
            metadata.media_sources.get(ms.name, MediaSourceMediaMetadata()),
        )
        for ms in media_sources
    ]

    # Detect stale media sources (in metadata but no longer on disk)
    stale_source_results = [
        _stale_source_result(ms_name, ms_meta)
        for ms_name, ms_meta in metadata.media_sources.items()
        if ms_name not in discovered_names
    ]

    all_results = [*source_results, *stale_source_results]

    return MediaMetadataCheck(
        has_media_metadata=True,
        image_count=sum(r.image_count for r in all_results),
        video_count=sum(r.video_count for r in all_results),
        new_keys=tuple(entry for r in all_results for entry in r.new),
        stale_keys=tuple(entry for r in all_results for entry in r.stale),
        duplicate_ids=_find_duplicate_ids(
            [uuid for r in all_results for uuid in r.uuids]
        ),
    )
