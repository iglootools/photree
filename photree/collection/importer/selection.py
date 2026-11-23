"""
Read collection import selection from ``to-import/`` and ``to-import.csv``.

Each entry is one of:
- An album directory name (e.g. ``2024-07-14 - Hiking the Rockies``)
- An album/collection/image/video ID (internal UUID or external ``prefix_<base58>``)
- A media filename (e.g. ``IMG_0410.HEIC``) — resolved by key + optional date hint

``to-import.csv`` is a two-column CSV with header: ``entry,date``.
The ``date`` column is an optional ISO timestamp for disambiguation.

``to-import/`` directory entries are physical files whose names are the
entries. For media files, EXIF dates are read to populate the date hint.
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from photree.album.exif import read_exif_timestamps_by_file
from photree.album.formats import IMG_EXTENSIONS, VID_EXTENSIONS
from photree.common.exif import ExifTagReader
from photree.common.fs import file_ext, list_files

SELECTION_DIR = "to-import"
SELECTION_CSV = "to-import.csv"

_MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS
_TIMESTAMP_FORMATS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


@dataclass(frozen=True)
class SelectionEntry:
    """A selection entry with optional date hint for disambiguation."""

    value: str
    date_hint: datetime | None = None


class SelectionErrorKind(StrEnum):
    """Why a selection row could not be used."""

    INVALID_DATE = "invalid-date"
    MISSING_ENTRY_COLUMN = "missing-entry-column"
    NOT_UTF8 = "not-utf8"
    MALFORMED_CSV = "malformed-csv"


@dataclass(frozen=True)
class SelectionError:
    """
    A selection CSV, or one of its rows, that cannot be used as written.

    ``line`` is the 1-based line number in the CSV (the header is line 1),
    so the user can jump straight to it; ``None`` when the problem is not
    tied to a line (a file that is not UTF-8). ``entry`` and ``value`` are
    the row's entry and offending value (the date for INVALID_DATE, the
    header for MISSING_ENTRY_COLUMN, the parser's reason for MALFORMED_CSV).
    """

    kind: SelectionErrorKind
    csv_path: Path
    line: int | None
    entry: str = ""
    value: str = ""


@dataclass(frozen=True)
class CollectionSelectionSources:
    """Selection entries collected from both sources."""

    dir_entries: tuple[SelectionEntry, ...]
    csv_entries: tuple[SelectionEntry, ...]
    merged: tuple[SelectionEntry, ...]
    errors: tuple[SelectionError, ...] = ()


def _parse_iso_timestamp(value: str) -> datetime | None:
    """Parse an ISO timestamp string, or ``None`` if no format matches."""
    return next(
        (
            parsed
            for fmt in _TIMESTAMP_FORMATS
            for parsed in [_strptime_or_none(value, fmt)]
            if parsed is not None
        ),
        None,
    )


def _strptime_or_none(value: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(value, fmt)
    except ValueError:
        return None


@dataclass(frozen=True)
class _CsvRow:
    line: int
    entry: str
    date: str  # "" when absent


_ENTRY_COLUMN = "entry"


def _read_csv_rows(csv_path: Path) -> tuple[list[_CsvRow], list[SelectionError]]:
    """
    Return the rows with a non-empty entry, or why the file cannot be read.

    Both are empty when the file does not exist or is empty. A file that
    exists but is unusable (not UTF-8, malformed, or without an ``entry``
    column, as a headerless file has) is an error rather than an empty
    selection: the import would otherwise succeed on ``to-import/`` alone
    and then delete the CSV, losing every row it holds. A UTF-8 byte order
    mark, which Excel writes on "CSV UTF-8" files, is accepted.
    """
    if not csv_path.is_file():
        return [], []
    try:
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            try:
                return _rows_of(reader, csv_path)
            except csv.Error as exc:
                return [], [
                    SelectionError(
                        SelectionErrorKind.MALFORMED_CSV,
                        csv_path,
                        reader.line_num,
                        value=str(exc),
                    ),
                ]
    except UnicodeDecodeError:
        return [], [SelectionError(SelectionErrorKind.NOT_UTF8, csv_path, None)]


def _rows_of(
    reader: csv.DictReader[str],
    csv_path: Path,
) -> tuple[list[_CsvRow], list[SelectionError]]:
    match reader.fieldnames:
        case None:
            return [], []
        case fieldnames if _ENTRY_COLUMN not in fieldnames:
            return [], [
                SelectionError(
                    SelectionErrorKind.MISSING_ENTRY_COLUMN,
                    csv_path,
                    1,
                    value=",".join(fieldnames),
                ),
            ]
        case _:
            rows = [
                _CsvRow(
                    line=reader.line_num,
                    entry=(row.get(_ENTRY_COLUMN) or "").strip(),
                    date=(row.get("date") or "").strip(),
                )
                for row in reader
            ]
            return [r for r in rows if r.entry], []


def _read_csv(
    csv_path: Path,
) -> tuple[list[SelectionEntry], list[SelectionError]]:
    """
    Read a two-column CSV (entry, date) with header.

    A date that matches none of the accepted formats is reported as a
    :class:`SelectionError` rather than dropped: it was written to
    disambiguate, so ignoring it could silently pick the wrong item.
    """
    csv_rows, read_errors = _read_csv_rows(csv_path)
    rows = [
        (row, _parse_iso_timestamp(row.date) if row.date else None) for row in csv_rows
    ]
    errors = [
        *read_errors,
        *(
            SelectionError(
                SelectionErrorKind.INVALID_DATE,
                csv_path,
                row.line,
                row.entry,
                row.date,
            )
            for row, parsed in rows
            if row.date and parsed is None
        ),
    ]
    entries = [
        SelectionEntry(value=row.entry, date_hint=parsed) for row, parsed in rows
    ]
    return entries, errors


def _is_media_file(filename: str) -> bool:
    return file_ext(filename) in _MEDIA_EXTENSIONS


def _read_dir_entries(
    selection_dir: Path,
    *,
    exiftool: ExifTagReader | None = None,
) -> list[SelectionEntry]:
    """
    Read entries from the selection directory.

    For media files, reads EXIF dates to populate ``date_hint``.
    For non-media files, the filename is the entry with no date hint.
    """
    filenames = list_files(selection_dir)
    # Separate media files (need EXIF) from non-media (IDs, names)
    media_files = [f for f in filenames if _is_media_file(f)]
    non_media_files = [f for f in filenames if not _is_media_file(f)]

    exif_dates = (
        {
            path.name: ts
            for path, ts in read_exif_timestamps_by_file(
                [selection_dir / f for f in media_files],
                exiftool=exiftool,
            )
        }
        if media_files
        else {}
    )
    return [
        *[SelectionEntry(value=f, date_hint=exif_dates.get(f)) for f in media_files],
        *[SelectionEntry(value=f) for f in non_media_files],
    ]


def _dedupe(entries: list[SelectionEntry]) -> tuple[SelectionEntry, ...]:
    """Deduplicate by value, keeping the first occurrence in order."""
    # Reversed so the dict keeps the *first* entry per value; the index then
    # restores the original order.
    first = {e.value: (i, e) for i, e in reversed(list(enumerate(entries)))}
    return tuple(e for _, e in sorted(first.values(), key=lambda pair: pair[0]))


def read_selection(
    collection_dir: Path,
    *,
    exiftool: ExifTagReader | None = None,
) -> CollectionSelectionSources:
    """
    Read selection entries from ``to-import/`` and ``to-import.csv``.

    Entries are deduplicated by value (first occurrence wins, dir entries
    first). For ``to-import/`` media files, EXIF dates are read into
    ``date_hint``. Unusable CSV rows are reported in ``errors``.
    """
    dir_entries = _read_dir_entries(collection_dir / SELECTION_DIR, exiftool=exiftool)
    csv_entries, csv_errors = _read_csv(collection_dir / SELECTION_CSV)
    return CollectionSelectionSources(
        dir_entries=tuple(dir_entries),
        csv_entries=tuple(csv_entries),
        merged=_dedupe([*dir_entries, *csv_entries]),
        errors=tuple(csv_errors),
    )


def has_selection(
    collection_dir: Path,
) -> bool:
    """
    Check whether *collection_dir* has anything to import.

    True when ``to-import/`` holds a file or ``to-import.csv`` has a row, or
    cannot be read: the import then reports why instead of the collection
    being skipped as having nothing to import. Reads no EXIF.
    """
    rows, errors = _read_csv_rows(collection_dir / SELECTION_CSV)
    return bool(list_files(collection_dir / SELECTION_DIR) or rows or errors)
