"""EXIF metadata extraction via exiftool subprocess.

This module isolates the exiftool dependency so it can be replaced with
a pure-Python library later.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from ..fsprotocol import (
    IMG_EXTENSIONS,
    IOS_DIR,
    MAIN_JPG_DIR,
    MAIN_VID_DIR,
    MOV_EXTENSIONS,
)

MEDIA_EXTENSIONS = IMG_EXTENSIONS | MOV_EXTENSIONS

# Keep low while iterating; increase for accuracy once stable.
DEFAULT_MAX_SAMPLES = 2


def check_exiftool_available() -> bool:
    """Check whether ``exiftool`` is on PATH."""
    return shutil.which("exiftool") is not None


def sample_media_files(
    album_dir: Path,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> list[Path]:
    """Pick up to *max_samples* random media files from an album.

    For iOS albums (``ios/`` subdir present), searches ``main-jpg/`` and
    ``main-vid/``.  For other albums, searches recursively from the album
    root.
    """
    if (album_dir / IOS_DIR).is_dir():
        search_dirs = [album_dir / MAIN_JPG_DIR, album_dir / MAIN_VID_DIR]
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


def read_exif_timestamps(files: list[Path]) -> list[datetime]:
    """Read the earliest available date tag from files using exiftool.

    Tries ``DateTimeOriginal`` first (photos), then falls back to
    ``CreateDate`` (videos).  Returns parsed timestamps for every line
    that exiftool successfully outputs.
    """
    if not files:
        return []

    result = subprocess.run(
        [
            "exiftool",
            "-DateTimeOriginal",
            "-CreateDate",
            "-s3",
            "-d",
            "%Y-%m-%dT%H:%M:%S",
            *files,
        ],
        capture_output=True,
        text=True,
    )

    timestamps: list[datetime] = []
    for line in result.stdout.strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped == "-":
            pass
        else:
            try:
                timestamps.append(datetime.strptime(stripped, "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                pass
    return timestamps


def read_album_min_timestamp(
    album_dir: Path,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> datetime | None:
    """Sample media files from an album and return the earliest EXIF timestamp."""
    files = sample_media_files(album_dir, max_samples)
    timestamps = read_exif_timestamps(files)
    return min(timestamps) if timestamps else None
