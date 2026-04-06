"""Read and merge photo selection from ``to-import/`` directory and ``to-import.csv``."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ...common.fs import list_files
from ..store.protocol import SELECTION_CSV, SELECTION_DIR
from .image_capture import _img_number


@dataclass(frozen=True)
class SelectionSources:
    """Selection filenames collected from both sources."""

    dir_files: tuple[str, ...]
    csv_files: tuple[str, ...]
    merged: tuple[str, ...]


def read_selection_csv(csv_path: Path) -> list[str]:
    """Read a one-column, no-header CSV of filenames.

    Returns an empty list when the file does not exist or is empty.
    Blank lines and leading/trailing whitespace are ignored.
    """
    if not csv_path.is_file():
        return []
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = csv.reader(f)
        return sorted(
            cell.strip() for row in rows if row for cell in row[:1] if cell.strip()
        )


def _merge_selections(dir_files: list[str], csv_files: list[str]) -> tuple[str, ...]:
    """Merge selection filenames from both sources, deduplicating by image number.

    When the same image number appears in both sources, the directory entry
    is preferred (actual exported file is more canonical than a CSV row).
    """
    seen: dict[str, str] = {}
    # Dir entries first so they win on conflict
    for f in dir_files:
        num = _img_number(f)
        seen.setdefault(num, f)
    for f in csv_files:
        num = _img_number(f)
        seen.setdefault(num, f)
    return tuple(sorted(seen.values()))


def read_selection(album_dir: Path) -> SelectionSources:
    """Read selection filenames from ``to-import/`` and ``to-import.csv``.

    Merges both sources with silent deduplication by image number.
    """
    dir_files = list_files(album_dir / SELECTION_DIR)
    csv_files = read_selection_csv(album_dir / SELECTION_CSV)
    merged = _merge_selections(dir_files, csv_files)
    return SelectionSources(
        dir_files=tuple(dir_files),
        csv_files=tuple(csv_files),
        merged=merged,
    )


def has_selection(album_dir: Path) -> bool:
    """Return True if the album has selection entries from either source."""
    sources = read_selection(album_dir)
    return len(sources.merged) > 0
