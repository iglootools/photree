"""Read collection import selection from ``to-import/`` and ``to-import.csv``.

Each entry is one of:
- An album directory name (e.g. ``2024-07-14 - Hiking the Rockies``)
- An album ID (internal UUID or external ``album_<base58>``)
- A collection directory name or collection ID
- An image or video ID (internal UUID or external ``image_<base58>``)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ...common.fs import list_files

SELECTION_DIR = "to-import"
SELECTION_CSV = "to-import.csv"


@dataclass(frozen=True)
class CollectionSelectionSources:
    """Selection entries collected from both sources."""

    dir_entries: tuple[str, ...]
    csv_entries: tuple[str, ...]
    merged: tuple[str, ...]


def _read_csv(csv_path: Path) -> list[str]:
    """Read a one-column, no-header CSV of entries.

    Returns an empty list when the file does not exist or is empty.
    """
    if not csv_path.is_file():
        return []
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = csv.reader(f)
        return [cell.strip() for row in rows if row for cell in row[:1] if cell.strip()]


def _read_dir_entries(selection_dir: Path) -> list[str]:
    """Read entry names from files in the selection directory.

    For collections, the filenames themselves are the entries (directory
    names, IDs, etc.). Unlike album import, the file contents are irrelevant.
    """
    return list_files(selection_dir)


def read_selection(collection_dir: Path) -> CollectionSelectionSources:
    """Read selection entries from ``to-import/`` and ``to-import.csv``.

    Entries are deduplicated (exact string match).
    """
    dir_entries = _read_dir_entries(collection_dir / SELECTION_DIR)
    csv_entries = _read_csv(collection_dir / SELECTION_CSV)
    seen: set[str] = set()
    merged: list[str] = []
    for entry in [*dir_entries, *csv_entries]:
        if entry not in seen:
            seen.add(entry)
            merged.append(entry)
    return CollectionSelectionSources(
        dir_entries=tuple(dir_entries),
        csv_entries=tuple(csv_entries),
        merged=tuple(merged),
    )


def has_selection(collection_dir: Path) -> bool:
    """Return True if the collection has selection entries from either source."""
    return len(read_selection(collection_dir).merged) > 0
