"""Low-level directory scanning for stats computation."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from ...common.fs import file_ext, list_files
from ..store.media_sources import dedup_media_dict as generic_dedup_media_dict
from ..store.protocol import (
    IMG_EXTENSIONS,
    SIDECAR_EXTENSIONS,
    VID_EXTENSIONS,
    MediaSource,
)
from .models import FormatStats, SizeStats

_ZERO_SIZE_STATS = SizeStats(file_count=0, apparent_bytes=0, on_disk_bytes=0)


def categorize_size_stats(
    directory: Path,
    seen_inodes: set[tuple[int, int]],
) -> tuple[SizeStats, SizeStats, SizeStats, tuple[FormatStats, ...]]:
    """Scan a directory and split results into images / videos / sidecars.

    Returns ``(images, videos, sidecars, by_format)`` where ``FormatStats``
    have ``archive_bytes=0`` and ``derived_bytes=0``.
    """
    files = list_files(directory)
    if not files:
        return _ZERO_SIZE_STATS, _ZERO_SIZE_STATS, _ZERO_SIZE_STATS, ()

    img_apparent = img_on_disk = img_count = 0
    vid_apparent = vid_on_disk = vid_count = 0
    sc_apparent = sc_on_disk = sc_count = 0
    format_apparent: Counter[str] = Counter()
    format_on_disk: Counter[str] = Counter()
    format_count: Counter[str] = Counter()

    for filename in files:
        path = directory / filename
        st = os.stat(path)
        size = st.st_size
        ext = file_ext(filename)
        inode_key = (st.st_dev, st.st_ino)
        is_new = inode_key not in seen_inodes
        if is_new:
            seen_inodes.add(inode_key)

        format_apparent[ext] += size
        format_count[ext] += 1

        if ext in IMG_EXTENSIONS:
            img_apparent += size
            img_count += 1
            if is_new:
                img_on_disk += size
                format_on_disk[ext] += size
        elif ext in VID_EXTENSIONS:
            vid_apparent += size
            vid_count += 1
            if is_new:
                vid_on_disk += size
                format_on_disk[ext] += size
        elif ext in SIDECAR_EXTENSIONS:
            sc_apparent += size
            sc_count += 1
            if is_new:
                sc_on_disk += size
                format_on_disk[ext] += size
        else:
            if is_new:
                format_on_disk[ext] += size

    by_format = tuple(
        FormatStats(
            extension=ext,
            file_count=format_count[ext],
            apparent_bytes=amt,
            on_disk_bytes=format_on_disk[ext],
            archive_bytes=0,
            derived_bytes=0,
        )
        for ext, amt in sorted(format_apparent.items(), key=lambda kv: -kv[1])
    )
    return (
        SizeStats(
            file_count=img_count, apparent_bytes=img_apparent, on_disk_bytes=img_on_disk
        ),
        SizeStats(
            file_count=vid_count, apparent_bytes=vid_apparent, on_disk_bytes=vid_on_disk
        ),
        SizeStats(
            file_count=sc_count, apparent_bytes=sc_apparent, on_disk_bytes=sc_on_disk
        ),
        by_format,
    )


def tag_format_role(
    fmts: tuple[FormatStats, ...],
    *,
    role: str,
) -> tuple[FormatStats, ...]:
    """Set archive_bytes or derived_bytes on format stats based on role."""
    match role:
        case "archive":
            return tuple(
                FormatStats(
                    extension=fs.extension,
                    file_count=fs.file_count,
                    apparent_bytes=fs.apparent_bytes,
                    on_disk_bytes=fs.on_disk_bytes,
                    archive_bytes=fs.apparent_bytes,
                    derived_bytes=0,
                )
                for fs in fmts
            )
        case "derived":
            return tuple(
                FormatStats(
                    extension=fs.extension,
                    file_count=fs.file_count,
                    apparent_bytes=fs.apparent_bytes,
                    on_disk_bytes=fs.on_disk_bytes,
                    archive_bytes=0,
                    derived_bytes=fs.apparent_bytes,
                )
                for fs in fmts
            )
        case _:
            return fmts


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
