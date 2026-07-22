"""Read and merge an iOS photo selection from a staging dir and/or a CSV.

The staging dir is ``to-import-ios-<name>/`` and the CSV is
``to-import-ios-<name>.csv``. Both are optional; when both are present their
entries are merged and deduplicated by image number.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from ...common.fs import list_files
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


def read_selection(
    selection_dir: Path | None,
    csv_path: Path | None,
) -> SelectionSources:
    """Read selection filenames from a staging dir and/or a CSV.

    Either source may be ``None`` (absent). Merges both with silent
    deduplication by image number.
    """
    dir_files = list_files(selection_dir) if selection_dir is not None else []
    csv_files = read_selection_csv(csv_path) if csv_path is not None else []
    merged = _merge_selections(dir_files, csv_files)
    return SelectionSources(
        dir_files=tuple(dir_files),
        csv_files=tuple(csv_files),
        merged=merged,
    )


def has_selection(
    selection_dir: Path | None,
    csv_path: Path | None,
) -> bool:
    """Return True if the sources yield at least one selection entry."""
    return len(read_selection(selection_dir, csv_path).merged) > 0
