"""Refresh album derived data — media IDs, EXIF cache, face detection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..common.fs import list_files
from ..fsprotocol import LinkMode, resolve_link_mode
from .browsable import refresh_browsable_dir
from .check.browsable import check_browsable_dir
from .check.jpeg import check_jpeg_dir
from .check.media_metadata import check_media_metadata
from .exif_cache.refresh import refresh_exif_cache
from .faces.detect import FaceAnalyzerFactory
from .faces.failures import FaceFailure
from .faces.refresh import refresh_face_data
from .id import generate_media_id
from .jpeg import (
    ConvertFile,
    JpegConversionFailure,
    convert_single_file,
    refresh_jpeg_dir,
)
from .live_photo import (
    augment_browsable_img_with_live_photo_videos,
    compute_live_photo_videos,
    detect_live_photo_keys,
    filter_live_photo_extras,
)
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
    VID_EXTENSIONS,
    KeyFn,
    MediaSource,
)


@dataclass(frozen=True)
class AlbumRefreshResult:
    """Outcome of :func:`refresh_album_derived_data`.

    Carries the per-file failures the refresh survived, so a caller can report
    them. A JPEG that failed to convert leaves a gap in ``{name}-jpg/`` that is
    otherwise invisible until the next ``album check``; an image whose face
    detection failed is silently missing from face clustering.

    Both fields are ``(media_source_name, failure)`` pairs.
    """

    jpeg_failures: tuple[tuple[str, JpegConversionFailure], ...] = ()
    face_failures: tuple[tuple[str, FaceFailure], ...] = ()

    @property
    def success(self) -> bool:
        return not self.jpeg_failures and not self.face_failures


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
    *,
    new_id: Callable[[], str] = generate_media_id,
) -> ReconcileResult:
    """Reconcile existing UUID->key mappings against current keys on disk."""
    existing_keys = set(existing.values())
    new_keys = sorted(current_keys - existing_keys)
    stale_keys = existing_keys - current_keys

    updated = {
        **{uuid: key for uuid, key in existing.items() if key in current_keys},
        **{new_id(): key for key in new_keys},
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
    key_fn: KeyFn,
) -> set[str]:
    """Scan a directory and return the set of deduped media keys."""
    return set(
        dedup_media_dict(list_files(album_dir / directory), extensions, key_fn).keys()
    )


def _media_extensions(ms: MediaSource) -> tuple[frozenset[str], frozenset[str]]:
    """Return ``(image_extensions, video_extensions)`` for a media source."""
    return (
        (IOS_IMG_EXTENSIONS, IOS_VID_EXTENSIONS)
        if ms.is_ios
        else (IMG_EXTENSIONS, VID_EXTENSIONS)
    )


def _refresh_media_source(
    album_dir: Path,
    ms: MediaSource,
    existing_ms: MediaSourceMediaMetadata,
    *,
    new_id: Callable[[], str],
) -> tuple[MediaSourceMediaMetadata, MediaSourceRefreshResult]:
    """Refresh a single media source — returns updated metadata and result."""
    img_ext, vid_ext = _media_extensions(ms)

    img = _reconcile(
        existing_ms.images,
        _scan_keys(album_dir, ms.orig_img_dir, img_ext, ms.key_fn),
        new_id=new_id,
    )
    vid = _reconcile(
        existing_ms.videos,
        _scan_keys(album_dir, ms.orig_vid_dir, vid_ext, ms.key_fn),
        new_id=new_id,
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
    new_id: Callable[[], str] = generate_media_id,
) -> RefreshResult:
    """Scan archive directories and reconcile with ``.photree/media-ids/``.

    Assigns new UUIDs (from *new_id*) to media files not yet tracked, removes
    stale entries for files no longer on disk.
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
                new_id=new_id,
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
    analyzer_factory: FaceAnalyzerFactory | None = None,
    force_browsable: bool = False,
    force_jpeg: bool = False,
    force_exif_cache: bool = False,
    convert_file: ConvertFile | None = None,
    redetect_faces: bool = False,
    refresh_face_thumbs: bool = False,
    dry_run: bool = False,
) -> AlbumRefreshResult:
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

    A shared *exiftool* instance and a memoized *analyzer_factory* can be
    passed to amortize startup cost across albums in batch operations. When
    *analyzer_factory* is ``None``, face detection is skipped.
    """
    media_sources = discover_media_sources(album_dir)

    _refresh_browsable_dirs(
        album_dir,
        media_sources,
        link_mode=link_mode or resolve_link_mode(None, album_dir),
        force=force_browsable,
        dry_run=dry_run,
    )
    jpeg_failures = _refresh_jpeg_dirs(
        album_dir,
        media_sources,
        max_workers=max_workers,
        convert_file=convert_file or convert_single_file,
        force=force_jpeg,
        dry_run=dry_run,
    )
    _refresh_media_ids_if_stale(album_dir, media_sources, dry_run=dry_run)
    refresh_exif_cache(
        album_dir, exiftool=exiftool, force=force_exif_cache, dry_run=dry_run
    )
    faces = refresh_face_data(
        album_dir,
        analyzer_factory=analyzer_factory,
        redetect=redetect_faces,
        refresh_thumbs=refresh_face_thumbs,
        dry_run=dry_run,
    )

    return AlbumRefreshResult(jpeg_failures=jpeg_failures, face_failures=faces.failures)


def _refresh_media_ids_if_stale(
    album_dir: Path, media_sources: list[MediaSource], *, dry_run: bool
) -> None:

    meta_check = check_media_metadata(album_dir, media_sources=media_sources)
    if meta_check is None or not meta_check.in_sync:
        refresh_media_metadata(album_dir, dry_run=dry_run)


def _refresh_browsable_dirs(
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    link_mode: LinkMode,
    force: bool,
    dry_run: bool,
) -> None:
    """Conditionally refresh browsable dirs for all media sources.

    Dry runs stop at the staleness check: nothing below it is called.
    """
    if dry_run:
        return
    for ms in media_sources:
        img_ext, vid_ext = _media_extensions(ms)
        if force or not _browsable_img_is_fresh(
            album_dir, ms, img_ext=img_ext, vid_ext=vid_ext, link_mode=link_mode
        ):
            _rebuild_browsable_img(album_dir, ms, img_ext, vid_ext, link_mode)
        if force or not _browsable_is_fresh(
            album_dir,
            ms.orig_vid_dir,
            ms.edit_vid_dir,
            ms.vid_dir,
            extensions=vid_ext,
            key_fn=ms.key_fn,
            link_mode=link_mode,
        ):
            _rebuild_browsable_vid(album_dir, ms, vid_ext, link_mode)


def _rebuild_browsable_img(
    album_dir: Path,
    ms: MediaSource,
    img_ext: frozenset[str],
    vid_ext: frozenset[str],
    link_mode: LinkMode,
) -> None:
    """Rebuild ``{name}-img/``, plus Live Photo companion videos for iOS."""
    refresh_browsable_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        media_extensions=img_ext,
        key_fn=ms.key_fn,
        link_mode=link_mode,
    )
    if ms.is_ios:
        augment_browsable_img_with_live_photo_videos(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            album_dir / ms.img_dir,
            vid_extensions=vid_ext,
            key_fn=ms.key_fn,
            link_mode=link_mode,
            dry_run=False,
        )


def _rebuild_browsable_vid(
    album_dir: Path, ms: MediaSource, vid_ext: frozenset[str], link_mode: LinkMode
) -> None:

    refresh_browsable_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        album_dir / ms.vid_dir,
        media_extensions=vid_ext,
        key_fn=ms.key_fn,
        link_mode=link_mode,
    )


def _browsable_is_fresh(
    album_dir: Path,
    orig_subdir: str,
    edit_subdir: str,
    browsable_subdir: str,
    *,
    extensions: frozenset[str],
    key_fn: KeyFn,
    link_mode: LinkMode,
) -> bool:
    """Return True if a browsable directory is consistent with its archive sources."""
    orig = album_dir / orig_subdir
    return not orig.is_dir() or (  # no archive → nothing to refresh
        check_browsable_dir(
            orig,
            album_dir / edit_subdir,
            album_dir / browsable_subdir,
            media_extensions=extensions,
            key_fn=key_fn,
            link_mode=link_mode,
            checksum=False,  # fast: file listing only, no content hashing
        ).success
    )


def _browsable_img_is_fresh(
    album_dir: Path,
    ms: MediaSource,
    *,
    img_ext: frozenset[str],
    vid_ext: frozenset[str],
    link_mode: LinkMode,
) -> bool:
    """Return True if the browsable img dir is consistent with archive sources.

    For iOS media sources, accounts for Live Photo companion videos that
    are expected to be present in the browsable img dir alongside images.
    """
    orig = album_dir / ms.orig_img_dir
    if not orig.is_dir():
        return True

    result = check_browsable_dir(
        orig,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        media_extensions=img_ext,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        checksum=False,
    )
    if not ms.is_ios:
        return result.success

    # For iOS, filter Live Photo videos from the "extra" list and verify
    # they are all present in the browsable dir.
    live_videos = _live_photo_vid_filenames(album_dir, ms, img_ext, vid_ext)
    browsable_files = frozenset(list_files(album_dir / ms.img_dir))
    return (
        filter_live_photo_extras(result, live_videos).success
        and live_videos <= browsable_files
    )


def _live_photo_vid_filenames(
    album_dir: Path,
    ms: MediaSource,
    img_ext: frozenset[str],
    vid_ext: frozenset[str],
) -> frozenset[str]:
    """Return expected Live Photo video filenames for a media source."""
    orig = album_dir / ms.orig_img_dir
    live_keys = detect_live_photo_keys(orig, img_ext, vid_ext, ms.key_fn)
    if not live_keys:
        return frozenset()
    videos = compute_live_photo_videos(
        orig, album_dir / ms.edit_img_dir, vid_ext, ms.key_fn
    )
    return frozenset(name for name, _ in videos)


def _refresh_jpeg_dirs(
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    max_workers: int | None,
    convert_file: ConvertFile,
    force: bool,
    dry_run: bool,
) -> tuple[tuple[str, JpegConversionFailure], ...]:
    """Conditionally refresh JPEG dirs for all media sources.

    Returns ``(media_source_name, failure)`` pairs for files that could not be
    converted, so the caller can report which source they belong to.
    """
    stale = [
        ms
        for ms in media_sources
        if (album_dir / ms.img_dir).is_dir()
        and (
            force
            or not check_jpeg_dir(
                album_dir / ms.img_dir, album_dir / ms.jpg_dir
            ).success
        )
    ]

    return tuple(
        (ms.name, failure)
        for ms in stale
        for failure in refresh_jpeg_dir(
            album_dir / ms.img_dir,
            album_dir / ms.jpg_dir,
            dry_run=dry_run,
            convert_file=convert_file,
            max_workers=max_workers,
        ).failed
    )
