"""Batch album rename planning from CSV input."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..album.naming import ParsedAlbumName, parse_album_name, reconstruct_name
from ..fs import ALBUM_ID_PREFIX, parse_external_id


@dataclass(frozen=True)
class RenameAction:
    """A planned album directory rename."""

    album_path: Path
    current_name: str
    new_name: str


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _has_mutable_changes(
    parsed: ParsedAlbumName,
    series: str | None,
    title: str,
    location: str | None,
) -> bool:
    return (
        _nfc(parsed.series or "") != _nfc(series or "")
        or _nfc(parsed.title) != _nfc(title)
        or _nfc(parsed.location or "") != _nfc(location or "")
    )


def _plan_row(row: dict[str, str], index: dict[str, Path]) -> RenameAction | str | None:
    """Process a single CSV row.

    Returns a :class:`RenameAction` when a rename is needed, an error
    string when the row is invalid, or ``None`` when no change is needed.
    """
    external_id = row.get("id", "").strip()
    if not external_id:
        return "Row with empty album ID"

    try:
        internal_id = parse_external_id(external_id, ALBUM_ID_PREFIX)
    except ValueError:
        return f"Invalid album ID format: {external_id}"

    album_path = index.get(internal_id)
    if album_path is None:
        return f"Album ID not found in gallery: {external_id}"

    parsed = parse_album_name(album_path.name)
    if parsed is None:
        return f"Cannot parse current album name: {album_path.name}"

    csv_series = row.get("series", "").strip() or None
    csv_title = row.get("title", "").strip()
    csv_location = row.get("location", "").strip() or None

    if not csv_title:
        return f"{external_id}: title is required but empty in CSV"

    if not _has_mutable_changes(parsed, csv_series, csv_title, csv_location):
        return None

    new_name = reconstruct_name(
        ParsedAlbumName(
            date=parsed.date,
            part=parsed.part,
            private=parsed.private,
            series=csv_series,
            title=csv_title,
            location=csv_location,
        )
    )
    return RenameAction(
        album_path=album_path,
        current_name=album_path.name,
        new_name=new_name,
    )


def plan_renames_from_csv(
    rows: list[dict[str, str]],
    index: dict[str, Path],
) -> tuple[tuple[RenameAction, ...], tuple[str, ...]]:
    """Plan album renames from CSV rows against the album index.

    Each row must contain ``id``, ``series``, ``title``, ``location`` columns.
    Other columns are ignored.  Immutable fields (``date``, ``part``,
    ``private``) come from the current on-disk album name.

    Returns ``(actions, errors)``.
    """
    results = [_plan_row(row, index) for row in rows]
    actions = tuple(r for r in results if isinstance(r, RenameAction))
    errors = tuple(r for r in results if isinstance(r, str))
    return actions, errors


class RenameCollisionError(ValueError):
    """Raised when a rename target conflicts with an existing directory."""

    def __init__(self, current_name: str, new_name: str) -> None:
        self.current_name = current_name
        self.new_name = new_name
        super().__init__(
            f"Collision: {current_name} → {new_name} "
            f"conflicts with existing directory"
        )


def check_rename_collisions(actions: tuple[RenameAction, ...]) -> None:
    """Check for target directory collisions among planned renames.

    Raises :class:`RenameCollisionError` if any target conflicts with
    an existing directory that is not itself being renamed.
    """
    renamed_resolved = {a.album_path.resolve() for a in actions}
    for action in actions:
        target = action.album_path.parent / action.new_name
        if (
            target.exists()
            and target.resolve() != action.album_path.resolve()
            and target.resolve() not in renamed_resolved
        ):
            raise RenameCollisionError(action.current_name, action.new_name)


def execute_renames(actions: tuple[RenameAction, ...]) -> int:
    """Execute planned renames. Returns the number of albums renamed."""
    for action in actions:
        new_path = action.album_path.parent / action.new_name
        action.album_path.rename(new_path)
    return len(actions)
