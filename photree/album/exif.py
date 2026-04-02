"""Album-specific EXIF conventions and helpers.

Defines project-specific tag priority and media extension sets,
and provides album-level convenience functions built on top of
the generic EXIF helpers in :mod:`common.exif`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..common.exif import (
    read_exif_timestamps as _generic_read_timestamps,
    read_exif_timestamps_by_file as _generic_read_by_file,
    set_exif_date as _generic_set_date,
)
from ..fs import discover_browsable_media_files

# Tag priority for timestamp extraction (first match wins):
#
# 1. CreationDate — QuickTime tag with timezone info. For edited iOS videos
#    (IMG_E*.MOV), this is the only tag that reflects the original capture
#    date. The other tags (CreateDate, ModifyDate) contain the UTC date/time
#    when the edit was rendered, which can be days after the shoot.
#
# 2. DateTimeOriginal — standard EXIF tag for photos (HEIC, JPEG, DNG).
#    Not present in QuickTime containers.
#
# 3. CreateDate — fallback for videos without CreationDate, or photos
#    without DateTimeOriginal.
#
# For photos, CreationDate is simply absent (QuickTime-only tag), so the
# priority naturally falls through to DateTimeOriginal.
_TIMESTAMP_TAGS = ["CreationDate", "DateTimeOriginal", "CreateDate"]


# ---------------------------------------------------------------------------
# Wrappers that bind _TIMESTAMP_TAGS
# ---------------------------------------------------------------------------


def read_exif_timestamps(
    files: list[Path],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[datetime]:
    """Read timestamps from files using the project's tag priority."""
    return _generic_read_timestamps(files, _TIMESTAMP_TAGS, exiftool=exiftool)


def read_exif_timestamps_by_file(
    files: list[Path],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[tuple[Path, datetime]]:
    """Read ``(file, timestamp)`` pairs using the project's tag priority."""
    return _generic_read_by_file(files, _TIMESTAMP_TAGS, exiftool=exiftool)


def set_exif_date(
    files: list[Path],
    date: str,
    *,
    log_cwd: Path | None = None,
) -> int:
    """Set the date portion of EXIF timestamps using the project's tag priority."""
    return _generic_set_date(files, date, _TIMESTAMP_TAGS, log_cwd=log_cwd)


def read_album_min_timestamp(
    album_dir: Path,
    *,
    exiftool: ExifToolHelper | None = None,
) -> datetime | None:
    """Read all media files from an album and return the earliest EXIF timestamp."""
    files = discover_browsable_media_files(album_dir)
    timestamps = read_exif_timestamps(files, exiftool=exiftool)
    return min(timestamps) if timestamps else None
