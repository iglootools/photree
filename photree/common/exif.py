"""
Generic EXIF metadata extraction and writing via exiftool.

This module provides exiftool process management and timestamp
extraction/writing helpers that are not specific to any album
layout or naming convention.
"""

import json
import shutil
import subprocess
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

# PyExifTool ships neither stubs nor a py.typed marker. This module is the only one
# that imports it: the others take an ExifTagReader.
from exiftool import ExifToolHelper  # pyright: ignore[reportMissingTypeStubs]

from photree.common.sysdeps import SystemDependency, WhichFn, is_available, require

_EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"
_EXIF_DATE_TZ_FORMAT = "%Y:%m:%d %H:%M:%S%z"


class ExifTagReader(Protocol):
    """Reads EXIF tags from files: a running ``ExifToolHelper``, or a test fake."""

    def get_tags(self, files: list[str], tags: list[str]) -> list[dict[str, object]]:
        """Return one ``{tag: value}`` mapping per file, in the order of *files*."""
        ...


def try_start_exiftool(*, which: WhichFn = shutil.which) -> ExifToolHelper | None:
    """
    Start a persistent exiftool process if the binary is installed.

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
    *,
    enabled: bool = True,
    which: WhichFn = shutil.which,
) -> Generator[ExifToolHelper | None]:
    """
    Yield a running exiftool helper (or ``None``), closing it on exit.

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
            # PyExifTool leaves __exit__'s parameters unannotated.
            et.__exit__(None, None, None)  # pyright: ignore[reportUnknownMemberType]


def parse_timestamp(value: str) -> datetime | None:
    """
    Parse an exiftool timestamp, with or without timezone.

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
    metadata: Mapping[str, object],
    tags: list[str],
) -> datetime | None:
    """
    Extract the best timestamp from a single file's metadata dict.

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
    exiftool: ExifTagReader | None = None,
    which: WhichFn = shutil.which,
) -> list[dict[str, object]]:
    """
    Fetch *tags* for *files* via exiftool.

    Raises :class:`~photree.common.sysdeps.MissingSystemDependencyError` when no
    helper is supplied and *which* does not find the binary — ``ExifToolHelper()`` would
    otherwise surface a bare ``FileNotFoundError`` that reads like a missing
    media file rather than a missing tool.

    Hands exiftool absolute paths: ``ExifToolHelper`` puts the files after the
    options with no end-of-options marker, so a relative path starting with a
    dash would be read as an option. An absolute path never starts with one.
    """
    if not files:
        return []
    str_files = [str(f.absolute()) for f in files]
    if exiftool is not None:
        return exiftool.get_tags(str_files, tags)
    else:
        require((SystemDependency.EXIFTOOL,), which=which)
        with ExifToolHelper() as et:
            return get_metadata(files, tags, exiftool=et)


def read_exif_timestamps(
    files: list[Path],
    tags: list[str],
    *,
    exiftool: ExifTagReader | None = None,
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
    exiftool: ExifTagReader | None = None,
) -> list[tuple[Path, datetime]]:
    """
    Read timestamps from files, returning ``(file, timestamp)`` pairs.

    Files whose timestamp cannot be read are silently skipped.
    """
    metadata_list = get_metadata(files, tags, exiftool=exiftool)
    return [
        (files[i], ts)
        for i, metadata in enumerate(metadata_list)
        if (ts := extract_timestamp(metadata, tags)) is not None
    ]


class ExifToolError(OSError):
    """
    An ``exiftool`` invocation exited non-zero.

    Carries the files it was run on, the exit code, and exiftool's stderr so
    the CLI layer can report *which* files failed and why. A plain class (not
    a frozen dataclass) because Python assigns ``__traceback__`` on raise.
    """

    def __init__(self, paths: Sequence[Path], returncode: int, stderr: str) -> None:
        """Build the error from the files, exiftool's exit code and its stderr."""
        super().__init__(f"exiftool exited with status {returncode}")
        self.paths = tuple(paths)
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True)
class ExifDateChange:
    """One file's EXIF timestamp before and after a date change."""

    path: Path
    original: str
    new_value: str


def _run_exiftool(args: Sequence[str], paths: Sequence[Path]) -> str:
    """
    Run ``exiftool *args* -- *paths*`` and return its stdout.

    The ``--`` ends the options: a relative path starting with a dash (as
    ``Path("./-AllDates=x.jpg")`` prints) would otherwise be read as an
    option or a tag assignment, and written to every other file.

    Raises :class:`ExifToolError` on a non-zero exit: exiftool reports
    per-file failures (unwritable file, unsupported format) through its exit
    status and stderr, and ignoring them would report unchanged files as
    updated.
    """
    result = subprocess.run(
        ["exiftool", *args, "--", *[str(p) for p in paths]],
        check=False,  # returncode is inspected below
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise ExifToolError(paths, result.returncode, result.stderr.strip())
    return result.stdout


# Writes each file in place, keeping its inode: ``-overwrite_original`` renames
# a new file over the old one, which silently detaches every hardlinked copy
# (the browsable dirs link the archive) and leaves it with the old dates.
_OVERWRITE_IN_PLACE = "-overwrite_original_in_place"


def _all_dates_args(assignment: str) -> list[str]:
    """Return the exiftool arguments applying *assignment* to every date tag."""
    return [f"-AllDates{assignment}", f"-CreationDate{assignment}"]


def _write_all_dates(paths: Sequence[Path], assignment: str) -> None:
    """Apply one tag *assignment* suffix (``=v``, ``+=v``, ``-=v``) to all dates."""
    _run_exiftool([*_all_dates_args(assignment), _OVERWRITE_IN_PLACE], paths)


def _argfile_path(path: Path) -> str:
    """
    Return *path* as an exiftool argfile line that reads back verbatim.

    Absolute, so it never reads as an option: ``--`` cannot be used in an
    argfile, where it would swallow the ``-execute`` separators too.
    ``#[CSTR]`` makes exiftool unescape the line as a C string, so a newline,
    a tab or edge whitespace in a file name survives instead of being split
    or stripped.
    """
    escaped = (
        str(path.absolute())
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f"#[CSTR]{escaped}"


def _write_dates_per_file(changes: Sequence[ExifDateChange]) -> None:
    """
    Write each change's own new value, all in one exiftool run.

    Starting exiftool costs 0.1-0.3 s, too much to pay per file. The run
    reads an argfile from stdin holding one ``-execute`` block per file;
    each block echoes its own exit status, so a failure is pinned on its file
    while the other files are still written.

    Raises :class:`ExifToolError` naming the files that failed.
    """
    if not changes:
        return
    blocks = [
        [
            *_all_dates_args(f"={c.new_value}"),
            "-echo3",
            "${status}",
            _argfile_path(c.path),
        ]
        for c in changes
    ]
    argfile = [
        *blocks[0],
        *(line for block in blocks[1:] for line in ("-execute", *block)),
    ]
    result = subprocess.run(
        ["exiftool", "-@", "-", "-common_args", "-q", _OVERWRITE_IN_PLACE],
        input="".join(f"{line}\n" for line in argfile),
        check=False,  # the per-file statuses and returncode are inspected below
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    failed = classify_failed_writes(
        [c.path for c in changes],
        result.stdout.split(),
        result.returncode,
    )
    if failed:
        raise ExifToolError(failed, result.returncode, result.stderr.strip())


def classify_failed_writes(
    paths: Sequence[Path],
    statuses: Sequence[str],
    returncode: int,
) -> tuple[Path, ...]:
    """
    Return the *paths* whose write failed, from the exit statuses echoed per file.

    *statuses* are the words of the run's stdout, one per path in order. When
    they cannot be matched to the paths (exiftool died mid-run, or is too old
    to expand ``${status}``), a non-zero *returncode* blames every path:
    which of them were written is unknown.
    """
    attributable = len(statuses) == len(paths) and all(s.isdigit() for s in statuses)
    match (attributable, returncode):
        case (True, _):
            return tuple(p for p, s in zip(paths, statuses, strict=True) if s != "0")
        case (False, 0):
            return ()
        case _:
            return tuple(paths)


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
    entry: dict[str, object],
    tags: Sequence[str],
    exif_date: str,
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
    """
    Set the date portion of EXIF timestamps, preserving the original time.

    *date* must be ``YYYY-MM-DD`` format.  Reads each file's existing
    timestamp, replaces the date part, and writes it back. Files without any
    of *tags* are left untouched and absent from the result.

    Raises :class:`ExifToolError` if reading fails, or naming the files
    whose write failed; every other file is written and keeps its new value.
    """
    exif_date = date.replace("-", ":")  # "2024:07:20"
    entries = json.loads(_run_exiftool(["-json", *[f"-{t}" for t in tags]], files))
    changes = tuple(
        change
        for entry in entries
        if (change := _date_change(entry, tags, exif_date)) is not None
    )
    _write_dates_per_file(changes)
    return changes


def set_exif_date_time(files: list[Path], timestamp: str) -> None:
    """
    Set the full EXIF timestamp on all files.

    *timestamp* is an ISO-like string (e.g. ``2024-07-20T13:55:20``
    or ``2024-07-20T13:55:20-06:00``). Raises :class:`ExifToolError` on
    failure.
    """
    # ISO separators to exiftool format: "2024-07-20T13:55:20" -> "2024:07:20 13:55:20"
    exif_ts = timestamp.replace("T", " ").replace("-", ":", 2)
    _write_all_dates(files, f"={exif_ts}")


def _shift(files: list[Path], spec: str, amount: int) -> None:
    """
    Shift all date tags by *amount* units of *spec*.

    *spec* is an exiftool ``Y:M:D H:M:S`` template with a ``{n}`` placeholder
    in the position being shifted; the sign of *amount* picks the operator.
    """
    op, n = ("+=", amount) if amount >= 0 else ("-=", -amount)
    _write_all_dates(files, f"{op}{spec.format(n=n)}")


def shift_exif_date(files: list[Path], days: int) -> None:
    """
    Shift EXIF timestamps by *days* (negative shifts backward).

    Raises :class:`ExifToolError` on failure.
    """
    _shift(files, "0:0:{n} 0:0:0", days)


def shift_exif_time(files: list[Path], hours: int) -> None:
    """
    Shift EXIF timestamps by *hours* (negative shifts backward).

    Raises :class:`ExifToolError` on failure.
    """
    _shift(files, "0:0:0 {n}:0:0", hours)
