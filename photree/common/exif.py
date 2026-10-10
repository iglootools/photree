"""Generic EXIF metadata extraction and writing via exiftool.

This module provides exiftool process management and timestamp
extraction/writing helpers that are not specific to any album
layout or naming convention.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from .sysdeps import SystemDependency, WhichFn, is_available, require

_EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"
_EXIF_DATE_TZ_FORMAT = "%Y:%m:%d %H:%M:%S%z"


# ---------------------------------------------------------------------------
# exiftool process management
# ---------------------------------------------------------------------------


def try_start_exiftool(*, which: WhichFn = shutil.which) -> ExifToolHelper | None:
    """Start a persistent exiftool process if the binary is installed.

    Returns ``None`` only when ``exiftool`` is not on PATH (EXIF checks are
    optional and degrade to "skipped"). A binary that is installed but fails
    to start raises: treating it as absent would silently skip every EXIF
    check on a machine that believes it has them. The caller must close the
    returned helper; prefer :func:`exiftool_session`.
    """
    if not is_available(SystemDependency.EXIFTOOL, which=which):
        return None
    et = ExifToolHelper()
    et.__enter__()
    return et


@contextmanager
def exiftool_session(
    *, enabled: bool = True, which: WhichFn = shutil.which
) -> Generator[ExifToolHelper | None, None, None]:
    """Yield a running exiftool helper (or ``None``), closing it on exit.

    ``None`` when *enabled* is false or exiftool is not installed. Use this
    instead of pairing :func:`try_start_exiftool` with a manual
    ``__exit__`` in a ``finally``: an early ``typer.Exit`` between the two
    leaks the process.
    """
    et = try_start_exiftool(which=which) if enabled else None
    try:
        yield et
    finally:
        if et is not None:
            et.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Timestamp reading
# ---------------------------------------------------------------------------


def parse_timestamp(value: str) -> datetime | None:
    """Parse an exiftool timestamp, with or without timezone.

    Always returns a **naive wall-clock** datetime: an offset, when present,
    is parsed and then dropped, keeping the local time as recorded by the
    camera. Album dates are wall-clock dates, so the local time is what the
    date checks need; and mixing aware values (``CreationDate``) with naive
    ones (``DateTimeOriginal``) would make ``min()``/comparisons raise.
    """
    for fmt in (_EXIF_DATE_TZ_FORMAT, _EXIF_DATE_FORMAT):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=None)
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
    """Fetch *tags* for *files* via exiftool.

    Raises :class:`~photree.common.sysdeps.MissingSystemDependencyError` when no
    helper is supplied and the binary is absent — ``ExifToolHelper()`` would
    otherwise surface a bare ``FileNotFoundError`` that reads like a missing
    media file rather than a missing tool.
    """
    if not files:
        return []
    str_files = [str(f) for f in files]
    if exiftool is not None:
        return exiftool.get_tags(str_files, tags)  # type: ignore[no-any-return]
    else:
        require((SystemDependency.EXIFTOOL,))
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


class ExifToolError(OSError):
    """An ``exiftool`` invocation exited non-zero.

    Carries the files it was run on, the exit code, and exiftool's stderr so
    the CLI layer can report *which* files failed and why. A plain class (not
    a frozen dataclass) because Python assigns ``__traceback__`` on raise.
    """

    def __init__(self, paths: Sequence[Path], returncode: int, stderr: str) -> None:
        super().__init__(f"exiftool exited with status {returncode}")
        self.paths = tuple(paths)
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True)
class ExifDateChange:
    """Record of a single file's EXIF date change."""

    path: Path
    original: str
    new_value: str


def _run_exiftool(args: Sequence[str], paths: Sequence[Path]) -> str:
    """Run ``exiftool *args* *paths*`` and return its stdout.

    Raises :class:`ExifToolError` on a non-zero exit: exiftool reports
    per-file failures (unwritable file, unsupported format) through its exit
    status and stderr, and ignoring them would report unchanged files as
    updated.
    """
    result = subprocess.run(
        ["exiftool", *args, *[str(p) for p in paths]],
        check=False,  # returncode is inspected below
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise ExifToolError(paths, result.returncode, result.stderr.strip())
    return result.stdout


def _write_all_dates(paths: Sequence[Path], assignment: str) -> None:
    """Apply one tag *assignment* suffix (``=v``, ``+=v``, ``-=v``) to all dates."""
    _run_exiftool(
        [f"-AllDates{assignment}", f"-CreationDate{assignment}", "-overwrite_original"],
        paths,
    )


def _first_timestamp(entry: dict[str, object], tags: Sequence[str]) -> str | None:
    """Return the first non-blank string value among *tags* in *entry*."""
    return next(
        (
            value
            for t in tags
            if isinstance(value := entry.get(t), str) and value.strip()
        ),
        None,
    )


def _date_change(
    entry: dict[str, object], tags: Sequence[str], exif_date: str
) -> ExifDateChange | None:
    """Plan the date replacement for one exiftool JSON *entry* (keeps the time)."""
    original = _first_timestamp(entry, tags)
    if original is None:
        return None
    else:
        _, sep, time = original.partition(" ")
        return ExifDateChange(
            path=Path(str(entry.get("SourceFile", ""))),
            original=original,
            new_value=f"{exif_date} {time if sep else '00:00:00'}",
        )


def write_exif_date(
    files: list[Path],
    date: str,
    tags: list[str],
) -> tuple[ExifDateChange, ...]:
    """Set the date portion of EXIF timestamps, preserving the original time.

    *date* must be ``YYYY-MM-DD`` format.  Reads each file's existing
    timestamp, replaces the date part, and writes it back. Files without any
    of *tags* are left untouched and absent from the result.

    Raises :class:`ExifToolError` if reading or any write fails; files
    written before the failure keep their new value.
    """
    exif_date = date.replace("-", ":")  # "2024:07:20"
    entries = json.loads(_run_exiftool(["-json", *[f"-{t}" for t in tags]], files))
    changes = tuple(
        change
        for entry in entries
        if (change := _date_change(entry, tags, exif_date)) is not None
    )
    for change in changes:
        _write_all_dates([change.path], f"={change.new_value}")
    return changes


def set_exif_date_time(files: list[Path], timestamp: str) -> None:
    """Set the full EXIF timestamp on all files.

    *timestamp* is an ISO-like string (e.g. ``2024-07-20T13:55:20``
    or ``2024-07-20T13:55:20-06:00``). Raises :class:`ExifToolError` on
    failure.
    """
    # ISO separators to exiftool format: "2024-07-20T13:55:20" -> "2024:07:20 13:55:20"
    exif_ts = timestamp.replace("T", " ").replace("-", ":", 2)
    _write_all_dates(files, f"={exif_ts}")


def _shift(files: list[Path], spec: str, amount: int) -> None:
    """Shift all date tags by *amount* units of *spec*.

    *spec* is an exiftool ``Y:M:D H:M:S`` template with a ``{n}`` placeholder
    in the position being shifted; the sign of *amount* picks the operator.
    """
    op, n = ("+=", amount) if amount >= 0 else ("-=", -amount)
    _write_all_dates(files, f"{op}{spec.format(n=n)}")


def shift_exif_date(files: list[Path], days: int) -> None:
    """Shift EXIF timestamps by *days* (negative shifts backward).

    Raises :class:`ExifToolError` on failure.
    """
    _shift(files, "0:0:{n} 0:0:0", days)


def shift_exif_time(files: list[Path], hours: int) -> None:
    """Shift EXIF timestamps by *hours* (negative shifts backward).

    Raises :class:`ExifToolError` on failure.
    """
    _shift(files, "0:0:0 {n}:0:0", hours)
