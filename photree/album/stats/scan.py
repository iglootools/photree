"""Low-level directory scanning for stats computation.

On-disk sizes are inode-deduplicated: a hardlinked file (browsable dirs are
usually hardlinks into the archive) is counted once across a whole album.
That needs state carried from one directory to the next — the set of inodes
already seen — which every function here takes and returns explicitly rather
than mutating a shared set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from ...common.fs import file_ext, list_files
from ..formats import (
    IMG_EXTENSIONS,
    IOS_IMG_EXTENSIONS,
    IOS_SIDECAR_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    VID_EXTENSIONS,
)
from ..live_photo import detect_live_photo_keys
from ..store.file_matching import dedup_media_dict as generic_dedup_media_dict
from ..store.media_source import MediaSource
from .aggregate import merge_size_stats
from .models import FormatStats, SizeStats, StorageRole

_ZERO = SizeStats(file_count=0, apparent_bytes=0, on_disk_bytes=0)

InodeKey = tuple[int, int]
"""``(st_dev, st_ino)`` — identifies a file's storage across hardlinks."""


def scan_directory_size(directory: Path) -> SizeStats:
    """Recursively compute file count and total size of a directory.

    Does not deduplicate inodes — face storage directories do not
    contain hardlinks.
    """
    sizes = (
        [entry.stat().st_size for entry in directory.rglob("*") if entry.is_file()]
        if directory.is_dir()
        else []
    )
    return SizeStats(
        file_count=len(sizes),
        apparent_bytes=sum(sizes),
        on_disk_bytes=sum(sizes),
    )


# ---------------------------------------------------------------------------
# File info extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FileInfo:
    """Stat result for a single file, and whether its inode is new."""

    ext: str
    size: int
    is_new_inode: bool


def _stat_files(
    directory: Path, seen_inodes: frozenset[InodeKey]
) -> tuple[tuple[_FileInfo, ...], frozenset[InodeKey]]:
    """Stat every file of *directory*, flagging inodes not in *seen_inodes*.

    Returns the infos and the updated set of seen inodes.
    """
    # Documented exception (docs/guidelines.md): loop-carried state — whether
    # an inode is new depends on the files stat'ed before it.
    infos: list[_FileInfo] = []
    seen = set(seen_inodes)
    for filename in list_files(directory):
        st = os.stat(directory / filename)
        inode = (st.st_dev, st.st_ino)
        infos.append(
            _FileInfo(
                ext=file_ext(filename), size=st.st_size, is_new_inode=inode not in seen
            )
        )
        seen.add(inode)
    return tuple(infos), frozenset(seen)


def _size_stats(infos: tuple[_FileInfo, ...]) -> SizeStats:
    return SizeStats(
        file_count=len(infos),
        apparent_bytes=sum(i.size for i in infos),
        on_disk_bytes=sum(i.size for i in infos if i.is_new_inode),
    )


def _format_stats(infos: tuple[_FileInfo, ...]) -> tuple[FormatStats, ...]:
    """Per-extension stats, sorted by apparent bytes descending."""
    by_ext = {
        ext: tuple(i for i in infos if i.ext == ext)
        for ext in sorted({i.ext for i in infos})
    }
    return tuple(
        sorted(
            (
                FormatStats(
                    extension=ext,
                    file_count=stats.file_count,
                    apparent_bytes=stats.apparent_bytes,
                    on_disk_bytes=stats.on_disk_bytes,
                    archive_bytes=0,
                    derived_bytes=0,
                )
                for ext, group in by_ext.items()
                for stats in [_size_stats(group)]
            ),
            key=lambda fs: -fs.apparent_bytes,
        )
    )


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------


class _Category(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    SIDECAR = "sidecar"
    OTHER = "other"


def _classify_ext(ext: str) -> _Category:
    """Classify a file extension into a media category."""
    match ext:
        case _ if ext in IMG_EXTENSIONS:
            return _Category.IMAGE
        case _ if ext in VID_EXTENSIONS:
            return _Category.VIDEO
        case _ if ext in IOS_SIDECAR_EXTENSIONS:
            return _Category.SIDECAR
        case _:
            return _Category.OTHER


@dataclass(frozen=True)
class DirStats:
    """Stats of one directory, split by media category.

    ``by_format`` has ``archive_bytes=0`` and ``derived_bytes=0``; see
    :func:`tag_format_role`.
    """

    images: SizeStats
    videos: SizeStats
    sidecars: SizeStats
    by_format: tuple[FormatStats, ...]

    @property
    def total(self) -> SizeStats:
        return merge_size_stats([self.images, self.videos, self.sidecars])


EMPTY_DIR_STATS = DirStats(images=_ZERO, videos=_ZERO, sidecars=_ZERO, by_format=())


def categorize_size_stats(
    directory: Path,
    seen_inodes: frozenset[InodeKey] = frozenset(),
) -> tuple[DirStats, frozenset[InodeKey]]:
    """Scan a directory and split results into images / videos / sidecars.

    Returns the stats and the updated set of seen inodes, to pass to the next
    directory of the same album.
    """
    infos, seen = _stat_files(directory, seen_inodes)

    def of(category: _Category) -> SizeStats:
        return _size_stats(tuple(i for i in infos if _classify_ext(i.ext) == category))

    return (
        DirStats(
            images=of(_Category.IMAGE),
            videos=of(_Category.VIDEO),
            sidecars=of(_Category.SIDECAR),
            by_format=_format_stats(infos),
        ),
        seen,
    )


# ---------------------------------------------------------------------------
# Format role tagging
# ---------------------------------------------------------------------------


def tag_format_role(
    fmts: tuple[FormatStats, ...],
    *,
    role: StorageRole,
) -> tuple[FormatStats, ...]:
    """Set archive_bytes or derived_bytes on format stats based on role."""
    match role:
        case StorageRole.ARCHIVE:
            return tuple(replace(fs, archive_bytes=fs.apparent_bytes) for fs in fmts)
        case StorageRole.DERIVED:
            return tuple(replace(fs, derived_bytes=fs.apparent_bytes) for fs in fmts)
        case StorageRole.BROWSABLE:
            return fmts


# ---------------------------------------------------------------------------
# Unique media counting
# ---------------------------------------------------------------------------


def count_unique_pictures(
    album_dir: Path, ms: MediaSource, *, has_archive: bool
) -> int:
    """Count unique pictures using the source's key function.

    When the archive directory exists on disk, counts from ``orig-img/``;
    otherwise falls back to the browsable ``{name}-img/`` directory.
    """
    directory = ms.orig_img_dir if has_archive else ms.img_dir
    return len(
        generic_dedup_media_dict(
            list_files(album_dir / directory), IMG_EXTENSIONS, ms.key_fn
        )
    )


def count_unique_videos(album_dir: Path, ms: MediaSource, *, has_archive: bool) -> int:
    """Count unique videos using the source's key function.

    When the archive directory exists on disk, counts from ``orig-vid/``;
    otherwise falls back to the browsable ``{name}-vid/`` directory.
    """
    directory = ms.orig_vid_dir if has_archive else ms.vid_dir
    return len(
        generic_dedup_media_dict(
            list_files(album_dir / directory), VID_EXTENSIONS, ms.key_fn
        )
    )


def count_live_photos(album_dir: Path, ms: MediaSource, *, has_archive: bool) -> int:
    """Count Live Photos — keys with both image and video in ``orig-img/``.

    Only meaningful for iOS media sources with archives. Returns 0 for
    std sources and sources without an archive directory.
    """
    if not has_archive or not ms.is_ios:
        return 0

    return len(
        detect_live_photo_keys(
            album_dir / ms.orig_img_dir,
            IOS_IMG_EXTENSIONS,
            IOS_VID_EXTENSIONS,
            ms.key_fn,
        )
    )
