"""EXIF metadata extraction via PyExifTool.

This module uses the PyExifTool library which maintains a persistent
exiftool process via the ``-stay_open`` protocol, avoiding per-call
subprocess overhead.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..fsprotocol import (
    IMG_EXTENSIONS,
    VID_EXTENSIONS,
    discover_contributors,
)

MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS

# Keep low while iterating; increase for accuracy once stable.
DEFAULT_MAX_SAMPLES = 2

_EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"
_TIMESTAMP_TAGS = ["DateTimeOriginal", "CreateDate"]


def check_exiftool_available() -> bool:
    """Check whether ``exiftool`` is on PATH."""
    return shutil.which("exiftool") is not None


def try_start_exiftool() -> ExifToolHelper | None:
    """Start a persistent exiftool process if available.

    Returns ``None`` when the ``exiftool`` binary is not installed or
    fails to start.  The caller must close the returned helper (use as
    a context manager or call ``__exit__`` in a ``finally`` block).
    """
    if not shutil.which("exiftool"):
        return None
    try:
        et = ExifToolHelper()
        et.__enter__()
        return et
    except (OSError, FileNotFoundError):
        return None


def sample_media_files(
    album_dir: Path,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> list[Path]:
    """Pick up to *max_samples* media files from an album.

    For iOS albums (any ``ios-*`` subdir present), searches all contributors'
    ``{name}-jpg/`` and ``{name}-vid/`` directories.  For other albums,
    searches recursively from the album root.
    """
    contributors = discover_contributors(album_dir)
    if contributors:
        search_dirs = [
            album_dir / d
            for c in contributors
            for d in (c.jpg_dir, c.vid_dir)
            if (album_dir / d).is_dir()
        ]
    else:
        search_dirs = [album_dir]

    candidates = [
        f
        for search_dir in search_dirs
        for f in search_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS
    ]

    if len(candidates) <= max_samples:
        return candidates
    # Deterministic: sort and take the first N for reproducible results
    return sorted(candidates)[:max_samples]


def _extract_timestamp(metadata: dict[str, object]) -> datetime | None:
    """Extract the best timestamp from a single file's metadata dict.

    Prefers ``DateTimeOriginal`` over ``CreateDate``.  Tag keys are
    group-prefixed (e.g. ``EXIF:DateTimeOriginal``) due to ExifToolHelper's
    default ``-G`` flag.
    """
    for tag in _TIMESTAMP_TAGS:
        for key, value in metadata.items():
            if key.endswith(f":{tag}") and isinstance(value, str) and value.strip():
                try:
                    return datetime.strptime(value.strip(), _EXIF_DATE_FORMAT)
                except ValueError:
                    pass
    return None


def read_exif_timestamps(
    files: list[Path],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[datetime]:
    """Read the earliest available date tag from files using exiftool.

    Tries ``DateTimeOriginal`` first (photos), then falls back to
    ``CreateDate`` (videos).  Returns parsed timestamps for every file
    that has a readable date tag.

    When *exiftool* is provided, the persistent process is reused.
    Otherwise a short-lived ``ExifToolHelper`` is created for this call.
    """
    if not files:
        return []

    str_files = [str(f) for f in files]

    if exiftool is not None:
        metadata_list = exiftool.get_tags(str_files, _TIMESTAMP_TAGS)
    else:
        with ExifToolHelper() as et:
            metadata_list = et.get_tags(str_files, _TIMESTAMP_TAGS)

    return [
        ts
        for metadata in metadata_list
        if (ts := _extract_timestamp(metadata)) is not None
    ]


def read_album_min_timestamp(
    album_dir: Path,
    max_samples: int = DEFAULT_MAX_SAMPLES,
    *,
    exiftool: ExifToolHelper | None = None,
) -> datetime | None:
    """Sample media files from an album and return the earliest EXIF timestamp."""
    files = sample_media_files(album_dir, max_samples)
    timestamps = read_exif_timestamps(files, exiftool=exiftool)
    return min(timestamps) if timestamps else None
