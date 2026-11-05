from datetime import datetime
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..common.exif import (
    ExifDateChange,
    write_exif_date,
)
from ..common.exif import (
    read_exif_timestamps_by_file as _generic_read_by_file,
)

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
    exiftool: ExifToolHelper | None = None,
) -> list[tuple[Path, datetime]]:
    return _generic_read_by_file(files, TIMESTAMP_TAGS, exiftool=exiftool)


def set_exif_date(
    files: list[Path],
    date: str,
) -> tuple[ExifDateChange, ...]:
    """Returns one change per file actually rewritten (see
    :func:`common.exif.write_exif_date`).
    """
    return write_exif_date(files, date, TIMESTAMP_TAGS)
