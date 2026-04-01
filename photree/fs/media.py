"""Generic media file matching utilities.

Provides key-function-parameterized grouping, deduplication, and file
finding that work for both iOS (image-number matching) and std
(filename-stem matching) media sources.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .fileutils import file_ext, list_files


# Preferred formats when multiple variants exist for the same key.
# DNG (ProRAW) is the highest-quality format, followed by HEIC (native iPhone).
# Tuple (not set) to express priority order: first match wins.
PICTURE_PRIORITY_EXTENSIONS = (".dng", ".heic")


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
    """Build a key→filename dict, preferring DNG > HEIC when duplicates exist.

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
