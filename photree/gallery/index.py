"""Gallery-level operations: album ID indexing and path lookups."""

from __future__ import annotations

import itertools
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..album.naming import ParsedAlbumName, parse_album_name, reconstruct_name
from ..fs import (
    ALBUM_ID_PREFIX,
    discover_albums,
    load_album_metadata,
    parse_external_id,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlbumIndex:
    """In-memory mapping of album IDs to their filesystem paths."""

    id_to_path: dict[str, Path]
    """Internal UUID → album path (first occurrence when duplicates exist)."""

    duplicates: dict[str, tuple[Path, ...]]
    """IDs that map to more than one album path."""


@dataclass(frozen=True)
class MissingAlbumIdError(Exception):
    """Raised when discovered albums lack a ``.photree/album.yaml`` ID."""

    albums: tuple[Path, ...]


@dataclass(frozen=True)
class RenameAction:
    """A planned album directory rename."""

    album_path: Path
    current_name: str
    new_name: str


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------


def build_album_id_to_path_index(gallery_dir: Path) -> AlbumIndex:
    """Scan all albums under *gallery_dir* and build an ID→path index.

    Raises :class:`MissingAlbumIdError` if any discovered album lacks an ID.
    """
    albums = discover_albums(gallery_dir)

    missing = tuple(
        album_dir for album_dir in albums if load_album_metadata(album_dir) is None
    )
    if missing:
        raise MissingAlbumIdError(albums=missing)

    pairs = [
        (meta.id, album_dir)
        for album_dir in albums
        if (meta := load_album_metadata(album_dir)) is not None
    ]

    sorted_pairs = sorted(pairs, key=lambda t: t[0])
    grouped = {
        aid: tuple(p for _, p in group)
        for aid, group in itertools.groupby(sorted_pairs, key=lambda t: t[0])
    }

    return AlbumIndex(
        id_to_path={aid: paths[0] for aid, paths in grouped.items()},
        duplicates={aid: paths for aid, paths in grouped.items() if len(paths) > 1},
    )


def resolve_album_path_by_id(index: dict[str, Path], album_id: str) -> Path:
    """Look up an album path by internal UUID.

    Raises :class:`KeyError` when *album_id* is not in the index.
    """
    try:
        return index[album_id]
    except KeyError:
        raise KeyError(f"Album ID not found in gallery index: {album_id}")


# ---------------------------------------------------------------------------
# Rename planning
# ---------------------------------------------------------------------------


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


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
    actions: list[RenameAction] = []
    errors: list[str] = []

    for row in rows:
        external_id = row.get("id", "").strip()
        if not external_id:
            errors.append("Row with empty album ID")
            continue

        # Parse external ID → internal UUID
        try:
            internal_id = parse_external_id(external_id, ALBUM_ID_PREFIX)
        except ValueError:
            errors.append(f"Invalid album ID format: {external_id}")
            continue

        # Look up album path
        album_path = index.get(internal_id)
        if album_path is None:
            errors.append(f"Album ID not found in gallery: {external_id}")
            continue

        # Parse current album name
        current_name = album_path.name
        parsed = parse_album_name(current_name)
        if parsed is None:
            errors.append(f"Cannot parse current album name: {current_name}")
            continue

        # Compare mutable fields
        csv_series = row.get("series", "").strip() or None
        csv_title = row.get("title", "").strip()
        csv_location = row.get("location", "").strip() or None

        if not csv_title:
            errors.append(f"{external_id}: title is required but empty in CSV")
            continue

        current_series = parsed.series
        current_title = parsed.title
        current_location = parsed.location

        series_changed = _nfc(current_series or "") != _nfc(csv_series or "")
        title_changed = _nfc(current_title) != _nfc(csv_title)
        location_changed = _nfc(current_location or "") != _nfc(csv_location or "")

        if not series_changed and not title_changed and not location_changed:
            continue

        # Build new name using immutable fields from disk + mutable from CSV
        new_parsed = ParsedAlbumName(
            date=parsed.date,
            part=parsed.part,
            private=parsed.private,
            series=csv_series,
            title=csv_title,
            location=csv_location,
        )
        new_name = reconstruct_name(new_parsed)
        actions.append(
            RenameAction(
                album_path=album_path,
                current_name=current_name,
                new_name=new_name,
            )
        )

    return (tuple(actions), tuple(errors))
