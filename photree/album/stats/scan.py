"""Low-level directory scanning for stats computation."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ...common.fs import file_ext, list_files
from ..store.media_sources import dedup_media_dict as generic_dedup_media_dict
from ..store.protocol import (
    IMG_EXTENSIONS,
    IOS_SIDECAR_EXTENSIONS,
    VID_EXTENSIONS,
    MediaSource,
)
from .models import FormatStats, SizeStats

_ZERO = SizeStats(file_count=0, apparent_bytes=0, on_disk_bytes=0)


def scan_directory_size(directory: Path) -> SizeStats:
    """Recursively compute file count and total size of a directory.

    Does not deduplicate inodes — face storage directories do not
    contain hardlinks.
    """
    if not directory.is_dir():
        return _ZERO

    file_count = 0
    total_bytes = 0
    for entry in directory.rglob("*"):
        if entry.is_file():
            file_count += 1
            total_bytes += entry.stat().st_size

    return SizeStats(
        file_count=file_count,
        apparent_bytes=total_bytes,
        on_disk_bytes=total_bytes,
    )


# ---------------------------------------------------------------------------
# File info extraction
# ---------------------------------------------------------------------------


@dataclass
class _FileInfo:
    """Stat result for a single file."""

    ext: str
    size: int
    is_new_inode: bool


def _stat_file(
    path: Path,
    filename: str,
    seen_inodes: set[tuple[int, int]],
) -> _FileInfo:
    """Stat a file and check inode novelty."""
    st = os.stat(path)
    inode_key = (st.st_dev, st.st_ino)
    is_new = inode_key not in seen_inodes
    if is_new:
        seen_inodes.add(inode_key)
    return _FileInfo(ext=file_ext(filename), size=st.st_size, is_new_inode=is_new)


# ---------------------------------------------------------------------------
# Size accumulator
# ---------------------------------------------------------------------------


@dataclass
class _SizeAccumulator:
    """Mutable accumulator for building a SizeStats."""

    file_count: int = 0
    apparent_bytes: int = 0
    on_disk_bytes: int = 0

    def add(self, info: _FileInfo) -> None:
        self.file_count += 1
        self.apparent_bytes += info.size
        if info.is_new_inode:
            self.on_disk_bytes += info.size

    def to_size_stats(self) -> SizeStats:
        return SizeStats(
            file_count=self.file_count,
            apparent_bytes=self.apparent_bytes,
            on_disk_bytes=self.on_disk_bytes,
        )


@dataclass
class _FormatAccumulator:
    """Mutable accumulator for per-extension stats."""

    apparent: Counter[str] = field(default_factory=Counter)
    on_disk: Counter[str] = field(default_factory=Counter)
    count: Counter[str] = field(default_factory=Counter)

    def add(self, info: _FileInfo) -> None:
        self.apparent[info.ext] += info.size
        self.count[info.ext] += 1
        if info.is_new_inode:
            self.on_disk[info.ext] += info.size

    def to_format_stats(self) -> tuple[FormatStats, ...]:
        return tuple(
            FormatStats(
                extension=ext,
                file_count=self.count[ext],
                apparent_bytes=amt,
                on_disk_bytes=self.on_disk[ext],
                archive_bytes=0,
                derived_bytes=0,
            )
            for ext, amt in sorted(self.apparent.items(), key=lambda kv: -kv[1])
        )


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------


def _classify_ext(ext: str) -> str:
    """Classify a file extension into a media category."""
    if ext in IMG_EXTENSIONS:
        return "img"
    elif ext in VID_EXTENSIONS:
        return "vid"
    elif ext in IOS_SIDECAR_EXTENSIONS:
        return "sidecar"
    else:
        return "other"


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
        return _ZERO, _ZERO, _ZERO, ()

    by_category: dict[str, _SizeAccumulator] = {
        "img": _SizeAccumulator(),
        "vid": _SizeAccumulator(),
        "sidecar": _SizeAccumulator(),
    }
    formats = _FormatAccumulator()

    for filename in files:
        info = _stat_file(directory / filename, filename, seen_inodes)
        formats.add(info)
        category = _classify_ext(info.ext)
        if category in by_category:
            by_category[category].add(info)

    return (
        by_category["img"].to_size_stats(),
        by_category["vid"].to_size_stats(),
        by_category["sidecar"].to_size_stats(),
        formats.to_format_stats(),
    )


# ---------------------------------------------------------------------------
# Format role tagging
# ---------------------------------------------------------------------------


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
