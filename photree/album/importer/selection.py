"""
Read and merge an iOS photo selection from a staging dir and/or a CSV.

The staging dir is ``to-import-ios-<name>/`` and the CSV is
``to-import-ios-<name>.csv``. Both are optional; when both are present their
entries are merged and deduplicated by image number.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from photree.album.store.media_source import ios_img_number
from photree.common.fs import list_files


@dataclass(frozen=True)
class SelectionSources:
    """
    An iOS selection's entries from each source, and both merged.

    *merged* holds one entry per image number, the staging dir's winning.
    """

    dir_files: tuple[str, ...]
    csv_files: tuple[str, ...]
    merged: tuple[str, ...]


def read_selection_csv(csv_path: Path) -> list[str]:
    """
    Read a selection CSV, returning an empty list when it is absent or empty.

    Blank lines and leading/trailing whitespace are ignored.
    """
    if not csv_path.is_file():
        return []
    with Path(csv_path).open(encoding="utf-8", newline="") as f:
        rows = csv.reader(f)
        return sorted(
            cell.strip() for row in rows if row for cell in row[:1] if cell.strip()
        )


def write_selection_csv(csv_path: Path, filenames: list[str]) -> None:
    """Write *filenames* as a one-column, no-header CSV (the format read back)."""
    with Path(csv_path).open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([name] for name in filenames)


def _merge_selections(dir_files: list[str], csv_files: list[str]) -> tuple[str, ...]:
    """
    Merge the directory and CSV selections, one entry per image number.

    When the same image number appears in both sources, the directory entry
    is preferred (actual exported file is more canonical than a CSV row).
    """
    # Later keys overwrite earlier ones in a dict, so building it from the
    # reversed sequence lets the first occurrence (dir entries first) win.
    by_number = {ios_img_number(f): f for f in reversed([*dir_files, *csv_files])}
    return tuple(sorted(by_number.values()))


def read_selection(
    selection_dir: Path | None,
    csv_path: Path | None,
) -> SelectionSources:
    """
    Read the selection from the staging directory and the CSV.

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
    """Return whether the staging dir and CSV together select any file."""
    return len(read_selection(selection_dir, csv_path).merged) > 0
