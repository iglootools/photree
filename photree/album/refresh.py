"""Refresh album derived data — media IDs, EXIF cache, face detection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]
from insightface.app import FaceAnalysis

from ..fsprotocol import LinkMode

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
# Composite refresh — all derived album data
# ---------------------------------------------------------------------------


def refresh_album_derived_data(
    album_dir: Path,
    *,
    link_mode: LinkMode | None = None,
    max_workers: int | None = None,
    exiftool: ExifToolHelper | None = None,
    face_analyzer: FaceAnalysis | None = None,
    force_browsable: bool = False,
    force_jpeg: bool = False,
    force_exif_cache: bool = False,
    convert_file: Callable[..., Path | None] | None = None,
    redetect_faces: bool = False,
    refresh_face_thumbs: bool = False,
    dry_run: bool = False,
) -> None:
    """Refresh all derived album data in a single pipeline.

    Runs 5 steps in order, each gated by a check to skip when up-to-date:

    1. **Browsable dirs** (main-img, main-vid) — gated by
       ``check_browsable_dir`` (no checksum, fast file-listing check).
    2. **JPEG dirs** (main-jpg) — gated by ``check_jpeg_dir``
       (file presence check).
    3. **Media IDs** — gated by ``check_media_metadata`` (``.in_sync``).
    4. **EXIF cache** — built-in mtime gate per file (more precise than
       the album check, which trusts the cache; the refresh checks
       actual mtimes because correctness matters more than speed here).
    5. **Face detection** — built-in mtime gate per file (same tradeoff
       as EXIF cache).

    The ``force_*`` flags bypass the check gate for the corresponding step.

    Shared instances (*exiftool*, *face_analyzer*) can be passed to
    amortize startup cost across albums in batch operations.
    """
    from .check.media_metadata import check_media_metadata
    from .exif_cache.refresh import refresh_exif_cache
    from .faces.refresh import refresh_face_data
    from .store.media_sources_discovery import discover_media_sources
    from ..fsprotocol import resolve_link_mode

    media_sources = discover_media_sources(album_dir)
    resolved_link_mode = link_mode or resolve_link_mode(None, album_dir)

    # 1. Browsable dirs (main-img, main-vid)
    _refresh_browsable_dirs(
        album_dir,
        media_sources,
        link_mode=resolved_link_mode,
        force=force_browsable,
        dry_run=dry_run,
    )

    # 2. JPEG dirs (main-jpg)
    _refresh_jpeg_dirs(
        album_dir,
        media_sources,
        max_workers=max_workers,
        convert_file=convert_file,
        force=force_jpeg,
        dry_run=dry_run,
    )

    # 3. Media IDs
    meta_check = check_media_metadata(album_dir, media_sources=media_sources)
    if meta_check is None or not meta_check.in_sync:
        refresh_media_metadata(album_dir, dry_run=dry_run)

    # 4. EXIF cache — built-in per-file mtime gate
    refresh_exif_cache(
        album_dir,
        exiftool=exiftool,
        force=force_exif_cache,
        dry_run=dry_run,
    )

    # 5. Face detection — built-in per-file mtime gate
    refresh_face_data(
        album_dir,
        face_analyzer=face_analyzer,
        redetect=redetect_faces,
        refresh_thumbs=refresh_face_thumbs,
        dry_run=dry_run,
    )


def _refresh_browsable_dirs(
    album_dir: Path,
    media_sources: list,
    *,
    link_mode: LinkMode,
    force: bool,
    dry_run: bool,
) -> None:
    """Conditionally refresh browsable dirs for all media sources."""
    from .browsable import refresh_browsable_dir
    from .store.protocol import (
        IMG_EXTENSIONS,
        IOS_IMG_EXTENSIONS,
        IOS_VID_EXTENSIONS,
        VID_EXTENSIONS,
    )

    for ms in media_sources:
        if not (album_dir / ms.archive_dir).is_dir():
            continue  # legacy std source — no archive to rebuild from

        img_ext = IOS_IMG_EXTENSIONS if ms.is_ios else IMG_EXTENSIONS
        vid_ext = IOS_VID_EXTENSIONS if ms.is_ios else VID_EXTENSIONS

        # main-img
        if force or not _browsable_is_fresh(
            album_dir,
            ms.orig_img_dir,
            ms.edit_img_dir,
            ms.img_dir,
            extensions=img_ext,
            key_fn=ms.key_fn,
            link_mode=link_mode,
        ):
            if not dry_run:
                refresh_browsable_dir(
                    album_dir / ms.orig_img_dir,
                    album_dir / ms.edit_img_dir,
                    album_dir / ms.img_dir,
                    media_extensions=img_ext,
                    key_fn=ms.key_fn,
                    link_mode=link_mode,
                    dry_run=dry_run,
                )

        # main-vid
        if force or not _browsable_is_fresh(
            album_dir,
            ms.orig_vid_dir,
            ms.edit_vid_dir,
            ms.vid_dir,
            extensions=vid_ext,
            key_fn=ms.key_fn,
            link_mode=link_mode,
        ):
            if not dry_run:
                refresh_browsable_dir(
                    album_dir / ms.orig_vid_dir,
                    album_dir / ms.edit_vid_dir,
                    album_dir / ms.vid_dir,
                    media_extensions=vid_ext,
                    key_fn=ms.key_fn,
                    link_mode=link_mode,
                    dry_run=dry_run,
                )


def _browsable_is_fresh(
    album_dir: Path,
    orig_subdir: str,
    edit_subdir: str,
    browsable_subdir: str,
    *,
    extensions: frozenset[str],
    key_fn: _KeyFn,
    link_mode: LinkMode,
) -> bool:
    """Return True if a browsable directory is consistent with its archive sources."""
    from .check.browsable import check_browsable_dir

    orig = album_dir / orig_subdir
    if not orig.is_dir():
        return True  # no archive → nothing to refresh

    result = check_browsable_dir(
        orig,
        album_dir / edit_subdir,
        album_dir / browsable_subdir,
        media_extensions=extensions,
        key_fn=key_fn,
        link_mode=link_mode,
        checksum=False,  # fast: file listing only, no content hashing
    )
    return result.success


def _refresh_jpeg_dirs(
    album_dir: Path,
    media_sources: list,
    *,
    max_workers: int | None,
    convert_file: Callable[..., Path | None] | None,
    force: bool,
    dry_run: bool,
) -> None:
    """Conditionally refresh JPEG dirs for all media sources."""
    from .check.jpeg import check_jpeg_dir
    from .jpeg import convert_single_file, refresh_jpeg_dir

    converter = convert_file if convert_file is not None else convert_single_file

    for ms in media_sources:
        img_dir = album_dir / ms.img_dir
        jpg_dir = album_dir / ms.jpg_dir

        if not img_dir.is_dir():
            continue

        if force or not check_jpeg_dir(img_dir, jpg_dir).success:
            refresh_jpeg_dir(
                img_dir,
                jpg_dir,
                dry_run=dry_run,
                convert_file=converter,
                max_workers=max_workers,
            )
