"""Generic EXIF metadata extraction and writing via exiftool.

This module provides exiftool process management and timestamp
extraction/writing helpers that are not specific to any album
layout or naming convention.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]
from rich.console import Console

from .formatting import CHECK

_console = Console(highlight=False)

_EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"
_EXIF_DATE_TZ_FORMAT = "%Y:%m:%d %H:%M:%S%z"


# ---------------------------------------------------------------------------
# exiftool process management
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Timestamp reading
# ---------------------------------------------------------------------------


def parse_timestamp(value: str) -> datetime | None:
    """Parse an exiftool timestamp, with or without timezone."""
    for fmt in (_EXIF_DATE_TZ_FORMAT, _EXIF_DATE_FORMAT):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def extract_timestamp(
    metadata: dict[str, object],
    tags: list[str],
) -> datetime | None:
    """Extract the best timestamp from a single file's metadata dict.

    Tries *tags* in priority order.  Tag keys are group-prefixed
    (e.g. ``EXIF:DateTimeOriginal``) due to ExifToolHelper's
    default ``-G`` flag.
    """
    for tag in tags:
        for key, value in metadata.items():
            if key.endswith(f":{tag}") and isinstance(value, str) and value.strip():
                ts = parse_timestamp(value.strip())
                if ts is not None:
                    return ts
    return None


def get_metadata(
    files: list[Path],
    tags: list[str],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[dict[str, object]]:
    """Fetch *tags* for *files* via exiftool."""
    if not files:
        return []
    str_files = [str(f) for f in files]
    if exiftool is not None:
        return exiftool.get_tags(str_files, tags)  # type: ignore[no-any-return]
    else:
        with ExifToolHelper() as et:
            return et.get_tags(str_files, tags)  # type: ignore[no-any-return]


def read_exif_timestamps(
    files: list[Path],
    tags: list[str],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[datetime]:
    """Read timestamps from files, returning only successfully parsed ones."""
    return [
        ts
        for metadata in get_metadata(files, tags, exiftool=exiftool)
        if (ts := extract_timestamp(metadata, tags)) is not None
    ]


def read_exif_timestamps_by_file(
    files: list[Path],
    tags: list[str],
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[tuple[Path, datetime]]:
    """Read timestamps from files, returning ``(file, timestamp)`` pairs.

    Files whose timestamp cannot be read are silently skipped.
    """
    metadata_list = get_metadata(files, tags, exiftool=exiftool)
    return [
        (files[i], ts)
        for i, metadata in enumerate(metadata_list)
        if (ts := extract_timestamp(metadata, tags)) is not None
    ]


# ---------------------------------------------------------------------------
# EXIF writing
# ---------------------------------------------------------------------------


def set_exif_date(
    files: list[Path],
    date: str,
    tags: list[str],
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
            *[f"-{t}" for t in tags],
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
                for t in tags
                if isinstance(entry.get(t), str) and entry[t].strip()
            ),
            None,
        )
        if not original:
            continue

        time_part = original.split(" ", 1)[1] if " " in original else "00:00:00"
        new_date = f"{exif_date} {time_part}"

        if log_cwd is not None:
            from ..fs import display_path

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
        from ..fs import display_path

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
        from ..fs import display_path

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


def shift_exif_time(
    files: list[Path],
    hours: int,
    *,
    log_cwd: Path | None = None,
) -> int:
    """Shift EXIF timestamps by a number of hours.

    Positive *hours* shifts forward, negative shifts backward.
    Returns the number of files updated.
    """
    import subprocess

    if hours >= 0:
        op = "+="
    else:
        op = "-="
        hours = -hours

    shift = f"0:0:0 {hours}:0:0"  # Y:M:D H:M:S

    if log_cwd is not None:
        from ..fs import display_path

        for f in files:
            _console.print(
                f"{CHECK} fix-exif shift {'+' if op == '+=' else '-'}{hours}h"
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
