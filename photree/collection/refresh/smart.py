"""Materialize date-range smart collection members (refresh phase 4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...dates import DateRange, date_range, range_contains
from ..naming import (
    parse_collection_name,
)
from ..store.metadata import (
    save_collection_metadata,
)
from ..store.protocol import (
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from .scan import AlbumInfo, ExistingCollection


@dataclass(frozen=True)
class _DatedMember:
    member_id: str
    start: date
    end: date
    private: bool


def _collection_range(col: ExistingCollection) -> DateRange | None:
    parsed = parse_collection_name(col.name)
    return date_range(parsed.date) if parsed.date is not None else None


def _smart_metadata(
    col: ExistingCollection,
    albums: tuple[_DatedMember, ...],
    collections: tuple[_DatedMember, ...],
) -> CollectionMetadata | None:
    """The members a date-range smart collection should have, or ``None``.

    ``None`` for collections whose members are not date-derived: manual ones,
    album-series ones (owned by the implicit refresh), and undated ones.
    Private smart collections only include private members; non-private ones
    exclude private members.
    """
    col_range = _collection_range(col)
    if (
        col.metadata.members != CollectionMembers.SMART
        or col.metadata.strategy == CollectionStrategy.ALBUM_SERIES
        or col_range is None
    ):
        return None
    private = parse_collection_name(col.name).private

    def contained(members: tuple[_DatedMember, ...]) -> list[str]:
        return sorted(
            m.member_id
            for m in members
            if m.member_id != col.metadata.id
            and m.private == private
            and range_contains(col_range, (m.start, m.end))
        )

    return CollectionMetadata(
        id=col.metadata.id,
        members=col.metadata.members,
        lifecycle=col.metadata.lifecycle,
        strategy=col.metadata.strategy,
        albums=contained(albums),
        collections=contained(collections),
        images=[],
        videos=[],
    )


def refresh_smart_collections(
    albums: tuple[AlbumInfo, ...],
    all_collections: tuple[ExistingCollection, ...],
    *,
    dry_run: bool,
) -> tuple[str, ...]:
    """Materialize members for smart collections by date range.

    Returns the names of the updated collections.
    """
    dated_albums = tuple(
        _DatedMember(album.album_id, *rng, album.parsed.private)
        for album in albums
        for rng in [date_range(album.parsed.date)]
        if rng is not None
    )
    dated_collections = tuple(
        _DatedMember(col.metadata.id, *rng, parse_collection_name(col.name).private)
        for col in all_collections
        for rng in [_collection_range(col)]
        if rng is not None
    )
    changed = [
        (col, new_meta)
        for col in all_collections
        for new_meta in [_smart_metadata(col, dated_albums, dated_collections)]
        if new_meta is not None and new_meta != col.metadata
    ]
    if not dry_run:
        for col, new_meta in changed:
            save_collection_metadata(col.path, new_meta)
    return tuple(col.name for col, _ in changed)
