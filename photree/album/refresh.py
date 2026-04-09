"""Refresh album derived data — media IDs, EXIF cache, face detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]
from insightface.app import FaceAnalysis

from ..common.fs import list_files
from .id import generate_media_id
from .store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    load_media_metadata,
    save_media_metadata,
)
from .store.media_sources import dedup_media_dict
from .store.media_sources_discovery import discover_media_sources
from .store.protocol import (
    IMG_EXTENSIONS,
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    MediaSource,
    VID_EXTENSIONS,
    _KeyFn,
)


@dataclass(frozen=True)
class ReconcileResult:
    """Result of reconciling existing UUID->key mappings against disk."""

    updated: dict[str, str]
    new_count: int
    removed_count: int


@dataclass(frozen=True)
class MediaSourceRefreshResult:
    """Result of refreshing media metadata for a single media source."""

    new_images: int
    new_videos: int
    removed_images: int
    removed_videos: int

    @property
    def changed(self) -> bool:
        return (
            self.new_images > 0
            or self.new_videos > 0
            or self.removed_images > 0
            or self.removed_videos > 0
        )


@dataclass(frozen=True)
class RefreshResult:
    """Result of refreshing media metadata for an album."""

    by_media_source: tuple[tuple[str, MediaSourceRefreshResult], ...]

    @property
    def total_new(self) -> int:
        return sum(r.new_images + r.new_videos for _, r in self.by_media_source)

    @property
    def total_removed(self) -> int:
        return sum(r.removed_images + r.removed_videos for _, r in self.by_media_source)

    @property
    def changed(self) -> bool:
        return any(r.changed for _, r in self.by_media_source)


def _reconcile(
    existing: dict[str, str],
    current_keys: set[str],
) -> ReconcileResult:
    """Reconcile existing UUID->key mappings against current keys on disk."""
    existing_keys = set(existing.values())
    new_keys = sorted(current_keys - existing_keys)
    stale_keys = existing_keys - current_keys

    updated = {
        **{uuid: key for uuid, key in existing.items() if key in current_keys},
        **{generate_media_id(): key for key in new_keys},
    }

    return ReconcileResult(
        updated=updated,
        new_count=len(new_keys),
        removed_count=len(stale_keys),
    )


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


def _refresh_media_source(
    album_dir: Path,
    ms: MediaSource,
    existing_ms: MediaSourceMediaMetadata,
) -> tuple[MediaSourceMediaMetadata, MediaSourceRefreshResult]:
    """Refresh a single media source — returns updated metadata and result."""
    img_ext = IOS_IMG_EXTENSIONS if ms.is_ios else IMG_EXTENSIONS
    vid_ext = IOS_VID_EXTENSIONS if ms.is_ios else VID_EXTENSIONS

    img = _reconcile(
        existing_ms.images,
        _scan_keys(album_dir, ms.orig_img_dir, img_ext, ms.key_fn),
    )
    vid = _reconcile(
        existing_ms.videos,
        _scan_keys(album_dir, ms.orig_vid_dir, vid_ext, ms.key_fn),
    )

    return (
        MediaSourceMediaMetadata(images=img.updated, videos=vid.updated),
        MediaSourceRefreshResult(
            new_images=img.new_count,
            new_videos=vid.new_count,
            removed_images=img.removed_count,
            removed_videos=vid.removed_count,
        ),
    )


def refresh_media_metadata(
    album_dir: Path,
    *,
    dry_run: bool = False,
) -> RefreshResult:
    """Scan archive directories and reconcile with ``.photree/media-ids/``.

    Assigns new UUIDs to media files not yet tracked, removes stale entries
    for files no longer on disk.
    """
    existing = load_media_metadata(album_dir) or MediaMetadata()
    sources = discover_media_sources(album_dir)

    refreshed = [
        (
            ms.name,
            *_refresh_media_source(
                album_dir,
                ms,
                existing.media_sources.get(ms.name, MediaSourceMediaMetadata()),
            ),
        )
        for ms in sources
    ]

    updated = MediaMetadata(
        media_sources={name: meta for name, meta, _ in refreshed},
    )
    if not dry_run:
        save_media_metadata(album_dir, updated)

    return RefreshResult(
        by_media_source=tuple((name, result) for name, _, result in refreshed),
    )


# ---------------------------------------------------------------------------
# Composite refresh (media IDs + EXIF cache + face detection)
# ---------------------------------------------------------------------------


def refresh_album_derived_data(
    album_dir: Path,
    *,
    exiftool: ExifToolHelper | None = None,
    face_analyzer: FaceAnalysis | None = None,
    redetect_faces: bool = False,
    refresh_face_thumbs: bool = False,
    dry_run: bool = False,
) -> None:
    """Refresh all derived album data: media IDs, EXIF cache, face detection.

    Shared instances (*exiftool*, *face_analyzer*) can be passed to
    amortize startup cost across albums in batch operations.
    """
    from .exif_cache.refresh import refresh_exif_cache
    from .faces.refresh import refresh_face_data

    refresh_media_metadata(album_dir, dry_run=dry_run)
    refresh_exif_cache(album_dir, exiftool=exiftool, dry_run=dry_run)
    refresh_face_data(
        album_dir,
        face_analyzer=face_analyzer,
        redetect=redetect_faces,
        refresh_thumbs=refresh_face_thumbs,
        dry_run=dry_run,
    )
