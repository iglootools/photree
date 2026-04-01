"""iOS Image Capture naming conventions and media file helpers."""

from __future__ import annotations

from pathlib import Path

from .fileutils import list_files
from .media import (
    PICTURE_PRIORITY_EXTENSIONS,
    dedup_media_dict as _generic_dedup,
    find_files_by_key,
    group_by_key,
    pick_media_priority,
)

# Re-export for backward compatibility
__all__ = [
    "PICTURE_PRIORITY_EXTENSIONS",
    "img_number",
    "pick_media_priority",
    "dedup_media_dict",
    "find_files_by_number",
    "find_files_by_stem",
]


def img_number(filename: str) -> str:
    """Extract the numeric portion of a filename (e.g. ``"0410"`` from ``"IMG_0410.HEIC"``)."""
    return "".join(c for c in filename if c.isdigit())


def _group_by_number(
    files: list[str], media_extensions: frozenset[str]
) -> dict[str, list[str]]:
    """Group media files by their numeric ID."""
    return group_by_key(files, media_extensions, img_number)


def dedup_media_dict(
    files: list[str], media_extensions: frozenset[str]
) -> dict[str, str]:
    """Build a number→filename dict, preferring DNG > HEIC when duplicates exist.

    iOS-specific convenience wrapper that uses :func:`img_number` as the
    key function. For a generic version, use :func:`media.dedup_media_dict`.
    """
    return _generic_dedup(files, media_extensions, img_number)


def find_files_by_number(
    numbers: set[str],
    directory: Path,
) -> list[str]:
    """Find all files in *directory* whose image number is in *numbers*."""
    return find_files_by_key(numbers, directory, img_number)


def find_files_by_stem(
    stems: set[str],
    directory: Path,
) -> list[str]:
    """Find all files in *directory* whose stem (name without extension) is in *stems*."""
    return sorted(f for f in list_files(directory) if Path(f).stem in stems)
