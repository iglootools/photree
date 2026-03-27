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
from rich.console import Console

from ..fsprotocol import (
    IMG_EXTENSIONS,
    VID_EXTENSIONS,
    discover_contributors,
)
from ..uiconventions import CHECK

_console = Console(highlight=False)

MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS

_EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"
_EXIF_DATE_TZ_FORMAT = "%Y:%m:%d %H:%M:%S%z"

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


def discover_media_files(album_dir: Path) -> list[Path]:
    """Collect all media files from an album.

    For albums with contributors, searches all contributors'
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

    return [
        f
        for search_dir in search_dirs
        for f in search_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS
    ]


def _extract_timestamp(metadata: dict[str, object]) -> datetime | None:
    """Extract the best timestamp from a single file's metadata dict.

    Prefers ``DateTimeOriginal`` over ``CreateDate``.  Tag keys are
    group-prefixed (e.g. ``EXIF:DateTimeOriginal``) due to ExifToolHelper's
    default ``-G`` flag.
    """
    for tag in _TIMESTAMP_TAGS:
        for key, value in metadata.items():
            if key.endswith(f":{tag}") and isinstance(value, str) and value.strip():
                ts = _parse_timestamp(value.strip())
                if ts is not None:
                    return ts
    return None


def _parse_timestamp(value: str) -> datetime | None:
    """Parse an exiftool timestamp, with or without timezone."""
    for fmt in (_EXIF_DATE_TZ_FORMAT, _EXIF_DATE_FORMAT):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def _get_metadata(
    files: list[Path],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[dict[str, object]]:
    """Fetch timestamp tags for *files* via exiftool."""
    if not files:
        return []
    str_files = [str(f) for f in files]
    if exiftool is not None:
        return exiftool.get_tags(str_files, _TIMESTAMP_TAGS)  # type: ignore[no-any-return]
    else:
        with ExifToolHelper() as et:
            return et.get_tags(str_files, _TIMESTAMP_TAGS)  # type: ignore[no-any-return]


def read_exif_timestamps(
    files: list[Path],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[datetime]:
    """Read timestamps from files, returning only successfully parsed ones."""
    return [
        ts
        for metadata in _get_metadata(files, exiftool=exiftool)
        if (ts := _extract_timestamp(metadata)) is not None
    ]


def read_exif_timestamps_by_file(
    files: list[Path],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[tuple[Path, datetime]]:
    """Read timestamps from files, returning ``(file, timestamp)`` pairs.

    Files whose timestamp cannot be read are silently skipped.
    """
    metadata_list = _get_metadata(files, exiftool=exiftool)
    return [
        (files[i], ts)
        for i, metadata in enumerate(metadata_list)
        if (ts := _extract_timestamp(metadata)) is not None
    ]


# ---------------------------------------------------------------------------
# EXIF writing
# ---------------------------------------------------------------------------


def set_exif_date(
    files: list[Path],
    date: str,
    *,
    log_cwd: Path | None = None,
) -> int:
    """Set the date portion of EXIF timestamps, preserving the original time.

    *date* must be ``YYYY-MM-DD`` format.  Reads each file's existing
    timestamp, replaces the date part, and writes it back.
    Returns the number of files updated.
    """
    import json
    import subprocess

    exif_date = date.replace("-", ":")  # "2024:07:20"

    result = subprocess.run(
        [
            "exiftool",
            "-json",
            *[f"-{t}" for t in _TIMESTAMP_TAGS],
            *[str(f) for f in files],
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0

    updated = 0
    for entry in json.loads(result.stdout):
        path = entry.get("SourceFile", "")
        original = next(
            (
                entry[t]
                for t in _TIMESTAMP_TAGS
                if isinstance(entry.get(t), str) and entry[t].strip()
            ),
            None,
        )
        if not original:
            continue

        time_part = original.split(" ", 1)[1] if " " in original else "00:00:00"
        new_date = f"{exif_date} {time_part}"

        if log_cwd is not None:
            from ..fsprotocol import display_path

            _console.print(
                f"{CHECK} fix-exif {display_path(Path(path), log_cwd)}: {original} -> {new_date}"
            )

        subprocess.run(
            [
                "exiftool",
                f"-AllDates={new_date}",
                f"-CreationDate={new_date}",
                "-overwrite_original",
                path,
            ],
            capture_output=True,
        )
        updated += 1

    return updated


def set_exif_date_time(
    files: list[Path],
    timestamp: str,
    *,
    log_cwd: Path | None = None,
) -> int:
    """Set the full EXIF timestamp on all files.

    *timestamp* is an ISO-like string (e.g. ``2024-07-20T13:55:20``
    or ``2024-07-20T13:55:20-06:00``).
    Returns the number of files updated.
    """
    import subprocess

    # Convert ISO separators to exiftool format: "2024-07-20T13:55:20" -> "2024:07:20 13:55:20"
    exif_ts = timestamp.replace("T", " ").replace("-", ":", 2)

    if log_cwd is not None:
        from ..fsprotocol import display_path

        for f in files:
            _console.print(f"{CHECK} fix-exif {display_path(f, log_cwd)}: -> {exif_ts}")

    result = subprocess.run(
        [
            "exiftool",
            f"-AllDates={exif_ts}",
            f"-CreationDate={exif_ts}",
            "-overwrite_original",
            *[str(f) for f in files],
        ],
    )
    return len(files) if result.returncode == 0 else 0


def shift_exif_date(
    files: list[Path],
    days: int,
    *,
    log_cwd: Path | None = None,
) -> int:
    """Shift EXIF timestamps by a number of days.

    Positive *days* shifts forward, negative shifts backward.
    Returns the number of files updated.
    """
    import subprocess

    if days >= 0:
        op = "+="
    else:
        op = "-="
        days = -days

    shift = f"0:0:{days} 0:0:0"  # Y:M:D H:M:S

    if log_cwd is not None:
        from ..fsprotocol import display_path

        for f in files:
            _console.print(
                f"{CHECK} fix-exif shift {'+' if op == '+=' else '-'}{days}d"
                f" {display_path(f, log_cwd)}"
            )

    result = subprocess.run(
        [
            "exiftool",
            f"-AllDates{op}{shift}",
            f"-CreationDate{op}{shift}",
            "-overwrite_original",
            *[str(f) for f in files],
        ],
    )
    return len(files) if result.returncode == 0 else 0


def read_album_min_timestamp(
    album_dir: Path,
    *,
    exiftool: ExifToolHelper | None = None,
) -> datetime | None:
    """Read all media files from an album and return the earliest EXIF timestamp."""
    files = discover_media_files(album_dir)
    timestamps = read_exif_timestamps(files, exiftool=exiftool)
    return min(timestamps) if timestamps else None
