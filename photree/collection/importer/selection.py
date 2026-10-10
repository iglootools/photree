"""Read collection import selection from ``to-import/`` and ``to-import.csv``.

Each entry is one of:
- An album directory name (e.g. ``2024-07-14 - Hiking the Rockies``)
- An album/collection/image/video ID (internal UUID or external ``prefix_<base58>``)
- A media filename (e.g. ``IMG_0410.HEIC``) — resolved by key + optional date hint

``to-import.csv`` is a two-column CSV with header: ``entry,date``.
The ``date`` column is an optional ISO timestamp for disambiguation.

``to-import/`` directory entries are physical files whose names are the
entries. For media files, EXIF dates are read to populate the date hint.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...album.exif import read_exif_timestamps_by_file
from ...album.formats import IMG_EXTENSIONS, VID_EXTENSIONS
from ...common.fs import file_ext, list_files

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


@dataclass(frozen=True)
class SelectionError:
    """A selection row that cannot be used as written.

    ``line`` is the 1-based line number in the CSV (the header is line 1),
    so the user can jump straight to it.
    """

    kind: SelectionErrorKind
    csv_path: Path
    line: int
    entry: str
    value: str


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


def _read_csv_rows(csv_path: Path) -> list[_CsvRow]:
    """Rows with a non-empty entry; empty when the file does not exist."""
    if not csv_path.is_file():
        return []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [
            _CsvRow(
                line=reader.line_num,
                entry=(row.get("entry") or "").strip(),
                date=(row.get("date") or "").strip(),
            )
            for row in reader
            if (row.get("entry") or "").strip()
        ]


def _read_csv(
    csv_path: Path,
) -> tuple[list[SelectionEntry], list[SelectionError]]:
    """Read a two-column CSV (entry, date) with header.

    A date that matches none of the accepted formats is reported as a
    :class:`SelectionError` rather than dropped: it was written to
    disambiguate, so ignoring it could silently pick the wrong item.
    """
    rows = [
        (row, _parse_iso_timestamp(row.date) if row.date else None)
        for row in _read_csv_rows(csv_path)
    ]
    errors = [
        SelectionError(
            SelectionErrorKind.INVALID_DATE, csv_path, row.line, row.entry, row.date
        )
        for row, parsed in rows
        if row.date and parsed is None
    ]
    entries = [
        SelectionEntry(value=row.entry, date_hint=parsed) for row, parsed in rows
    ]
    return entries, errors


def _is_media_file(filename: str) -> bool:
    """Check if a filename has a recognized media extension."""
    return file_ext(filename) in _MEDIA_EXTENSIONS


def _read_dir_entries(
    selection_dir: Path,
    *,
    exiftool: ExifToolHelper | None = None,
) -> list[SelectionEntry]:
    """Read entries from the selection directory.

    For media files, reads EXIF dates to populate ``date_hint``.
    For non-media files, the filename is the entry with no date hint.
    """
    filenames = list_files(selection_dir)
    # Separate media files (need EXIF) from non-media (IDs, names)
    media_files = [f for f in filenames if _is_media_file(f)]
    non_media_files = [f for f in filenames if not _is_media_file(f)]

    # Read EXIF dates for media files in one batch
    exif_dates = (
        {
            path.name: ts
            for path, ts in read_exif_timestamps_by_file(
                [selection_dir / f for f in media_files], exiftool=exiftool
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
    exiftool: ExifToolHelper | None = None,
) -> CollectionSelectionSources:
    """Read selection entries from ``to-import/`` and ``to-import.csv``.

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
    """Return True if the collection has selection entries from either source."""
    # Quick check without EXIF reading
    return bool(list_files(collection_dir / SELECTION_DIR)) or bool(
        _read_csv_rows(collection_dir / SELECTION_CSV)
    )
