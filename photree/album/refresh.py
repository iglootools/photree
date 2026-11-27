"""Refresh of an album's derived data: media IDs, browsable dirs, JPEGs, caches."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from photree.album.browsable import refresh_browsable_dir
from photree.album.check.browsable import (
    check_browsable_dir,
    filter_live_photo_extras,
)
from photree.album.check.jpeg import check_jpeg_dir
from photree.album.check.media_metadata import check_media_metadata
from photree.album.exif_cache.refresh import refresh_exif_cache
from photree.album.faces.detect import FaceAnalyzerFactory
from photree.album.faces.failures import FaceFailure
from photree.album.faces.refresh import refresh_face_data
from photree.album.id import generate_media_id
from photree.album.jpeg import (
    ConvertFile,
    JpegConversionFailure,
    convert_single_file,
    refresh_jpeg_dir,
)
from photree.album.live_photo import (
    augment_browsable_img_with_live_photo_videos,
    compute_live_photo_videos,
    detect_live_photo_keys,
)
from photree.album.store.file_matching import scan_media_keys
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    load_media_metadata,
    save_media_metadata,
)
from photree.album.store.media_source import KeyFn, MediaSource
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.common.exif import ExifTagReader
from photree.common.fs import list_files
from photree.foundation.linking import LinkMode


@dataclass(frozen=True)
class AlbumRefreshResult:
    """
    The outcome of a refresh, with the per-file failures it survived.

    Carries them so a caller can report them. A JPEG that failed to convert
    leaves a gap in ``{name}-jpg/`` that is otherwise invisible until the next
    ``album check``; an image whose face detection failed is silently missing
    from face clustering.

    Both fields are ``(media_source_name, failure)`` pairs.
    """

    jpeg_failures: tuple[tuple[str, JpegConversionFailure], ...] = ()
    face_failures: tuple[tuple[str, FaceFailure], ...] = ()

    @property
    def success(self) -> bool:
        """Return whether no JPEG conversion or face detection failed."""
        return not self.jpeg_failures and not self.face_failures


@dataclass(frozen=True)
class ReconcileResult:
    """
    The media IDs after reconciling them with the keys present on disk.

    *updated* maps each media ID to its key; the counts are the keys that
    got a new ID and the IDs dropped because their key is gone.
    """

    updated: dict[str, str]
    new_count: int
    removed_count: int


@dataclass(frozen=True)
class MediaSourceRefreshResult:
    """The media IDs one media source gained and lost, for images and videos."""

    new_images: int
    new_videos: int
    removed_images: int
    removed_videos: int
    reassigned: int = 0
    """Items given a new ID because an earlier item of the album held theirs."""

    @property
    def changed(self) -> bool:
        """Return whether any media ID was added, removed or reassigned."""
        return (
            self.new_images > 0
            or self.new_videos > 0
            or self.removed_images > 0
            or self.removed_videos > 0
            or self.reassigned > 0
        )


@dataclass(frozen=True)
class RefreshResult:
    """The outcome of refreshing an album's media IDs, per media source name."""

    by_media_source: tuple[tuple[str, MediaSourceRefreshResult], ...]

    @property
    def total_new(self) -> int:
        """Return the number of new media IDs across every media source."""
        return sum(r.new_images + r.new_videos for _, r in self.by_media_source)

    @property
    def changed(self) -> bool:
        """Return whether any media source's media IDs changed."""
        return any(r.changed for _, r in self.by_media_source)


def _reconcile(
    existing: dict[str, str],
    current_keys: set[str],
    *,
    new_id: Callable[[], str] = generate_media_id,
) -> ReconcileResult:
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


def _refresh_media_source(
    album_dir: Path,
    ms: MediaSource,
    existing_ms: MediaSourceMediaMetadata,
    *,
    new_id: Callable[[], str],
) -> tuple[MediaSourceMediaMetadata, MediaSourceRefreshResult]:
    img = _reconcile(
        existing_ms.images,
        scan_media_keys(album_dir / ms.orig_img_dir, ms.img_extensions, ms.key_fn),
        new_id=new_id,
    )
    vid = _reconcile(
        existing_ms.videos,
        scan_media_keys(album_dir / ms.orig_vid_dir, ms.vid_extensions, ms.key_fn),
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


def _reassign_duplicate_ids(
    metadata: MediaMetadata,
    *,
    new_id: Callable[[], str],
) -> tuple[MediaMetadata, dict[str, int]]:
    """
    Give a new ID to every item whose ID an earlier item of the album holds.

    Order is media source, then images before videos, then file order. Returns
    the metadata and the number of IDs reassigned per media source.
    """
    slots = [
        (name, is_video, uuid)
        for name, ms_meta in metadata.media_sources.items()
        for is_video, ids in ((False, ms_meta.images), (True, ms_meta.videos))
        for uuid in ids
    ]
    first_slot = {uuid: i for i, (_, _, uuid) in reversed(list(enumerate(slots)))}
    duplicates = {
        (name, is_video, uuid)
        for i, (name, is_video, uuid) in enumerate(slots)
        if first_slot[uuid] != i
    }

    def remint(name: str, ids: dict[str, str], *, is_video: bool) -> dict[str, str]:
        return {
            (new_id() if (name, is_video, uuid) in duplicates else uuid): key
            for uuid, key in ids.items()
        }

    return (
        MediaMetadata(
            media_sources={
                name: MediaSourceMediaMetadata(
                    images=remint(name, ms_meta.images, is_video=False),
                    videos=remint(name, ms_meta.videos, is_video=True),
                )
                for name, ms_meta in metadata.media_sources.items()
            },
        ),
        {
            name: sum(1 for owner, _, _ in duplicates if owner == name)
            for name in metadata.media_sources
        },
    )


def refresh_media_metadata(
    album_dir: Path,
    *,
    dry_run: bool = False,
    new_id: Callable[[], str] = generate_media_id,
) -> RefreshResult:
    """
    Bring the media IDs in sync with the files on disk.

    Assigns new UUIDs (from *new_id*) to media files not yet tracked, removes
    stale entries for files no longer on disk, and gives a new UUID to each
    item whose UUID another item of the album already holds, which ``album
    check`` reports as a duplicate ID.
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

    updated, reassigned = _reassign_duplicate_ids(
        MediaMetadata(media_sources={name: meta for name, meta, _ in refreshed}),
        new_id=new_id,
    )
    if not dry_run:
        save_media_metadata(album_dir, updated)

    return RefreshResult(
        by_media_source=tuple(
            (name, replace(result, reassigned=reassigned[name]))
            for name, _, result in refreshed
        ),
    )


def refresh_album_derived_data(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    max_workers: int | None = None,
    exiftool: ExifTagReader | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
    force_browsable: bool = False,
    force_jpeg: bool = False,
    force_exif_cache: bool = False,
    convert_file: ConvertFile | None = None,
    redetect_faces: bool = False,
    refresh_face_thumbs: bool = False,
    dry_run: bool = False,
) -> AlbumRefreshResult:
    """
    Refresh an album's derived data, skipping each step that is up to date.

    Runs 5 steps in order, each gated by a check:

    1. **Browsable dirs** (main-img, main-vid) — gated by
       ``check_browsable_dir`` (no checksum, fast file-listing check).
    2. **JPEG dirs** (main-jpg) — gated by ``check_jpeg_dir``
       (file presence check), and always regenerated for a media source
       whose browsable img dir step 1 rebuilt: the presence check cannot
       see an image whose content changed under the same name.
    3. **Media IDs** — gated by ``check_media_metadata`` (``.in_sync``).
    4. **EXIF cache** — built-in mtime gate per file (more precise than
       the album check, which trusts the cache; the refresh checks
       actual mtimes because correctness matters more than speed here).
    5. **Face detection** — built-in mtime gate per file (same tradeoff
       as EXIF cache).

    The ``force_*`` flags bypass the check gate for the corresponding step.
    *link_mode* is resolved by the caller (CLI option or ``gallery.yaml``):
    looking up the gallery is the CLI layer's job.

    A shared *exiftool* instance and a memoized *analyzer_factory* can be
    passed to amortize startup cost across albums in batch operations. When
    *analyzer_factory* is ``None``, face detection is skipped.
    """
    media_sources = discover_media_sources(album_dir)

    rebuilt_img = _refresh_browsable_dirs(
        album_dir,
        media_sources,
        link_mode=link_mode,
        force=force_browsable,
        dry_run=dry_run,
    )
    jpeg_failures = _refresh_jpeg_dirs(
        album_dir,
        media_sources,
        max_workers=max_workers,
        convert_file=convert_file or convert_single_file,
        force=force_jpeg,
        forced_sources=rebuilt_img,
        dry_run=dry_run,
    )
    _refresh_media_ids_if_stale(album_dir, media_sources, dry_run=dry_run)
    refresh_exif_cache(
        album_dir,
        exiftool=exiftool,
        force=force_exif_cache,
        dry_run=dry_run,
    )
    faces = refresh_face_data(
        album_dir,
        analyzer_factory=analyzer_factory,
        redetect=redetect_faces,
        refresh_thumbs=refresh_face_thumbs,
        dry_run=dry_run,
        max_workers=max_workers,
    )

    return AlbumRefreshResult(jpeg_failures=jpeg_failures, face_failures=faces.failures)


def _refresh_media_ids_if_stale(
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    dry_run: bool,
) -> None:

    meta_check = check_media_metadata(album_dir, media_sources=media_sources)
    if not meta_check.in_sync:
        refresh_media_metadata(album_dir, dry_run=dry_run)


def _refresh_browsable_dirs(
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    link_mode: LinkMode,
    force: bool,
    dry_run: bool,
) -> frozenset[str]:
    """
    Rebuild each stale browsable dir; return the sources whose img dir was rebuilt.

    Dry runs return before any staleness check: nothing below it is called.
    """
    if dry_run:
        return frozenset()
    rebuilt_img = frozenset(
        ms.name
        for ms in media_sources
        if _refresh_browsable_img(album_dir, ms, link_mode=link_mode, force=force)
    )
    for ms in media_sources:
        if force or not _browsable_is_fresh(
            album_dir,
            ms.orig_vid_dir,
            ms.edit_vid_dir,
            ms.vid_dir,
            extensions=ms.vid_extensions,
            key_fn=ms.key_fn,
            link_mode=link_mode,
        ):
            _rebuild_browsable_vid(album_dir, ms, link_mode)
    return rebuilt_img


def _refresh_browsable_img(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode,
    force: bool,
) -> bool:
    """Rebuild ``{name}-img/`` when forced or stale; return whether it was rebuilt."""
    stale = force or not _browsable_img_is_fresh(album_dir, ms, link_mode=link_mode)
    if stale:
        _rebuild_browsable_img(album_dir, ms, link_mode)
    return stale


def _rebuild_browsable_img(
    album_dir: Path,
    ms: MediaSource,
    link_mode: LinkMode,
) -> None:
    """Rebuild ``{name}-img/``, plus Live Photo companion videos for iOS."""
    refresh_browsable_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        media_extensions=ms.img_extensions,
        key_fn=ms.key_fn,
        link_mode=link_mode,
    )
    if ms.is_ios:
        augment_browsable_img_with_live_photo_videos(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            album_dir / ms.img_dir,
            vid_extensions=ms.vid_extensions,
            key_fn=ms.key_fn,
            link_mode=link_mode,
            dry_run=False,
        )


def _rebuild_browsable_vid(
    album_dir: Path,
    ms: MediaSource,
    link_mode: LinkMode,
) -> None:

    refresh_browsable_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        album_dir / ms.vid_dir,
        media_extensions=ms.vid_extensions,
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
    link_mode: LinkMode,
) -> bool:
    """
    Tell whether the browsable img dir is up to date.

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
        media_extensions=ms.img_extensions,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        checksum=False,
    )
    if not ms.is_ios:
        return result.success

    # For iOS, filter Live Photo videos from the "extra" list and verify
    # they are all present in the browsable dir.
    live_videos = _live_photo_vid_filenames(album_dir, ms)
    browsable_files = frozenset(list_files(album_dir / ms.img_dir))
    return (
        filter_live_photo_extras(result, live_videos).success
        and live_videos <= browsable_files
    )


def _live_photo_vid_filenames(album_dir: Path, ms: MediaSource) -> frozenset[str]:
    orig = album_dir / ms.orig_img_dir
    live_keys = detect_live_photo_keys(
        orig,
        ms.img_extensions,
        ms.vid_extensions,
        ms.key_fn,
    )
    if not live_keys:
        return frozenset()
    videos = compute_live_photo_videos(
        orig,
        album_dir / ms.edit_img_dir,
        ms.vid_extensions,
        ms.key_fn,
    )
    return frozenset(name for name, _ in videos)


def _refresh_jpeg_dirs(
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    max_workers: int | None,
    convert_file: ConvertFile,
    force: bool,
    forced_sources: frozenset[str],
    dry_run: bool,
) -> tuple[tuple[str, JpegConversionFailure], ...]:
    """
    Refresh each JPEG dir, returning the files that could not be converted.

    A JPEG dir is refreshed when *force* is set, when its source is in
    *forced_sources*, or when a JPEG is missing or extra. Returns
    ``(media_source_name, failure)`` pairs, so the caller can report which
    source they belong to.
    """
    stale = [
        ms
        for ms in media_sources
        if (album_dir / ms.img_dir).is_dir()
        and (
            force
            or ms.name in forced_sources
            or not check_jpeg_dir(
                album_dir / ms.img_dir,
                album_dir / ms.jpg_dir,
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


# What callers that refresh an album take, so a test can pass a fake refresh.
type RefreshFn = Callable[..., AlbumRefreshResult]
