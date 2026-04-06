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
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...album.exif import read_exif_timestamps_by_file
from ...album.store.protocol import IMG_EXTENSIONS, VID_EXTENSIONS
from ...common.fs import file_ext, list_files

SELECTION_DIR = "to-import"
SELECTION_CSV = "to-import.csv"

_MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS


@dataclass(frozen=True)
class SelectionEntry:
    """A selection entry with optional date hint for disambiguation."""

    value: str
    date_hint: datetime | None = None


@dataclass(frozen=True)
class CollectionSelectionSources:
    """Selection entries collected from both sources."""

    dir_entries: tuple[SelectionEntry, ...]
    csv_entries: tuple[SelectionEntry, ...]
    merged: tuple[SelectionEntry, ...]


def _parse_iso_timestamp(value: str) -> datetime | None:
    """Parse an ISO timestamp string, returning None on failure."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def _read_csv(csv_path: Path) -> list[SelectionEntry]:
    """Read a two-column CSV (entry, date) with header.

    Returns an empty list when the file does not exist or is empty.
    """
    if not csv_path.is_file():
        return []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [
            SelectionEntry(
                value=row["entry"].strip(),
                date_hint=(
                    _parse_iso_timestamp(row["date"].strip())
                    if row.get("date", "").strip()
                    else None
                ),
            )
            for row in reader
            if row.get("entry", "").strip()
        ]


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
    if not filenames:
        return []

    # Separate media files (need EXIF) from non-media (IDs, names)
    media_files = [f for f in filenames if _is_media_file(f)]
    non_media_files = [f for f in filenames if not _is_media_file(f)]

    # Read EXIF dates for media files in one batch
    exif_dates: dict[str, datetime] = {}
    if media_files:
        media_paths = [selection_dir / f for f in media_files]
        for path, ts in read_exif_timestamps_by_file(media_paths, exiftool=exiftool):
            exif_dates[path.name] = ts

    return [
        *[SelectionEntry(value=f, date_hint=exif_dates.get(f)) for f in media_files],
        *[SelectionEntry(value=f) for f in non_media_files],
    ]


def read_selection(
    collection_dir: Path,
    *,
    exiftool: ExifToolHelper | None = None,
) -> CollectionSelectionSources:
    """Read selection entries from ``to-import/`` and ``to-import.csv``.

    Entries are deduplicated by value (first occurrence wins).
    For ``to-import/`` media files, EXIF dates are read into ``date_hint``.
    """
    dir_entries = _read_dir_entries(collection_dir / SELECTION_DIR, exiftool=exiftool)
    csv_entries = _read_csv(collection_dir / SELECTION_CSV)
    # Deduplicate by value, preserving order (dir entries first)
    seen: set[str] = set()
    merged: list[SelectionEntry] = []
    for entry in [*dir_entries, *csv_entries]:
        if entry.value not in seen:
            seen.add(entry.value)
            merged.append(entry)
    return CollectionSelectionSources(
        dir_entries=tuple(dir_entries),
        csv_entries=tuple(csv_entries),
        merged=tuple(merged),
    )


def has_selection(
    collection_dir: Path,
) -> bool:
    """Return True if the collection has selection entries from either source."""
    # Quick check without EXIF reading
    dir_files = list_files(collection_dir / SELECTION_DIR)
    if dir_files:
        return True
    csv_path = collection_dir / SELECTION_CSV
    if not csv_path.is_file():
        return False
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return any(row.get("entry", "").strip() for row in reader)
