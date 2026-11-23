"""
Media file matching utilities.

Provides key-function-parameterized grouping, deduplication, and file
finding that work for both iOS (image-number matching) and std
(filename-stem matching) media sources.

Also includes iOS-specific (``ios_find_files_by_number``) and std-specific
(``std_find_files_by_stem``) convenience wrappers. The key functions
themselves live with :class:`~.media_source.MediaSource`.
"""

from collections.abc import Callable
from itertools import groupby
from pathlib import Path

from photree.album.formats import (
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    PICTURE_PRIORITY_EXTENSIONS,
)
from photree.album.store.media_source import ios_img_number
from photree.common.fs import file_ext, list_files


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
    """
    Group files by key.

    Groups are ordered by key; within a group, files keep their input order
    (the sort is stable), which :func:`pick_media_priority` relies on for its
    fallback.
    """
    media = sorted((f for f in files if file_ext(f) in media_extensions), key=key_fn)
    return {key: list(group) for key, group in groupby(media, key=key_fn)}


def dedup_media_dict(
    files: list[str],
    media_extensions: frozenset[str],
    key_fn: Callable[[str], str],
) -> dict[str, str]:
    """Build a key->filename dict, preferring DNG > HEIC when duplicates exist."""
    return {
        key: (pick_media_priority(candidates) if len(candidates) > 1 else candidates[0])
        for key, candidates in group_by_key(files, media_extensions, key_fn).items()
    }


def scan_media_keys(
    directory: Path,
    media_extensions: frozenset[str],
    key_fn: Callable[[str], str],
) -> set[str]:
    """Return the keys of the media files in *directory* (none if it is missing)."""
    return set(dedup_media_dict(list_files(directory), media_extensions, key_fn))


def find_files_by_key(
    keys: set[str],
    directory: Path,
    key_fn: Callable[[str], str],
) -> list[str]:
    """Return the sorted names of the files in *directory* whose key is in *keys*."""
    return sorted(f for f in list_files(directory) if key_fn(f) in keys)


def ios_is_media(filename: str) -> bool:
    """Tell whether *filename* has an iOS image or video extension."""
    ext = file_ext(filename)
    return ext in IOS_IMG_EXTENSIONS or ext in IOS_VID_EXTENSIONS


def ios_file_prefix(filename: str) -> str:
    """
    Return the prefix of an iOS file name.

    ``IMG_E`` → ``'E'`` (edited), ``IMG_O`` → ``'O'`` (edited metadata),
    ``IMG_`` → ``''`` (original).
    """
    match filename.lower()[:5]:
        case "img_e":
            return "E"
        case "img_o":
            return "O"
        case _:
            return ""


def ios_find_files_by_number(
    numbers: set[str],
    directory: Path,
) -> list[str]:
    """Return the sorted names of the files in *directory* numbered in *numbers*."""
    return find_files_by_key(numbers, directory, ios_img_number)


def std_find_files_by_stem(
    stems: set[str],
    directory: Path,
) -> list[str]:
    """Return the sorted names of the files in *directory* with a stem in *stems*."""
    return sorted(f for f in list_files(directory) if Path(f).stem in stems)
