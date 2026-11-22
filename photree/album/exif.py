"""Read and write the EXIF capture dates of an album's media files."""

from datetime import datetime
from pathlib import Path

from photree.common.exif import ExifDateChange, ExifTagReader, write_exif_date
from photree.common.exif import read_exif_timestamps_by_file as _generic_read_by_file

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
TIMESTAMP_TAGS = ["CreationDate", "DateTimeOriginal", "CreateDate"]


def read_exif_timestamps_by_file(
    files: list[Path],
    *,
    exiftool: ExifTagReader | None = None,
) -> list[tuple[Path, datetime]]:
    """
    Return ``(file, capture timestamp)`` pairs for the *files* whose date is readable.

    Reads the tags in :data:`TIMESTAMP_TAGS` order and silently skips files with
    none of them. Runs a transient exiftool when *exiftool* is ``None``.
    """
    return _generic_read_by_file(files, TIMESTAMP_TAGS, exiftool=exiftool)


def set_exif_date(
    files: list[Path],
    date: str,
) -> tuple[ExifDateChange, ...]:
    """
    Set the EXIF date of an album's files, returning one change per file rewritten.

    See :func:`common.exif.write_exif_date`.
    """
    return write_exif_date(files, date, TIMESTAMP_TAGS)
