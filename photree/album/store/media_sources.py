"""Media source file matching utilities.

Provides key-function-parameterized grouping, deduplication, and file
finding that work for both iOS (image-number matching) and std
(filename-stem matching) media sources.

Also includes iOS-specific convenience wrappers (``img_number``,
``find_files_by_number``, ``find_files_by_stem``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...common.fs import file_ext, list_files
from .protocol import PICTURE_PRIORITY_EXTENSIONS

# ---------------------------------------------------------------------------
# Generic (key-function-parameterized) utilities
# ---------------------------------------------------------------------------


def pick_media_priority(candidates: list[str]) -> str:
    """Pick the highest-priority file from candidates (DNG > HEIC > others)."""
    return next(
        (
            f
            for ext in PICTURE_PRIORITY_EXTENSIONS
            for f in candidates
            if file_ext(f) == ext
        ),
        candidates[0],
    )


def group_by_key(
    files: list[str],
    media_extensions: frozenset[str],
    key_fn: Callable[[str], str],
) -> dict[str, list[str]]:
    """Group media files by a key extracted via *key_fn*."""
    groups: dict[str, list[str]] = {}
    for f in files:
        if file_ext(f) in media_extensions:
            groups.setdefault(key_fn(f), []).append(f)
    return groups


def dedup_media_dict(
    files: list[str],
    media_extensions: frozenset[str],
    key_fn: Callable[[str], str],
) -> dict[str, str]:
    """Build a key->filename dict, preferring DNG > HEIC when duplicates exist.

    Groups files by *key_fn* and picks the highest-quality format when
    multiple variants share the same key.
    """
    return {
        key: (pick_media_priority(candidates) if len(candidates) > 1 else candidates[0])
        for key, candidates in group_by_key(files, media_extensions, key_fn).items()
    }


def find_files_by_key(
    keys: set[str],
    directory: Path,
    key_fn: Callable[[str], str],
) -> list[str]:
    """Find all files in *directory* whose key (via *key_fn*) is in *keys*."""
    return sorted(f for f in list_files(directory) if key_fn(f) in keys)


# ---------------------------------------------------------------------------
# iOS-specific convenience wrappers
# ---------------------------------------------------------------------------


def img_number(filename: str) -> str:
    """Extract the numeric portion of a filename (e.g. ``"0410"`` from ``"IMG_0410.HEIC"``)."""
    return "".join(c for c in filename if c.isdigit())


def ios_dedup_media_dict(
    files: list[str], media_extensions: frozenset[str]
) -> dict[str, str]:
    """Build a number->filename dict, preferring DNG > HEIC when duplicates exist.

    iOS-specific convenience wrapper that uses :func:`img_number` as the
    key function.
    """
    return dedup_media_dict(files, media_extensions, img_number)


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
