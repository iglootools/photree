"""Materialize date-range smart collection members (refresh phase 4)."""

from dataclasses import dataclass
from datetime import date

from photree.collection.naming import parse_collection_name
from photree.collection.refresh.result import CollectionRefreshError, filesystem_error
from photree.collection.refresh.scan import AlbumInfo, ExistingCollection
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from photree.dates import DateRange, date_range, range_contains


@dataclass(frozen=True)
class SmartChanges:
    """The smart collections whose members were updated, and a write that failed."""

    updated: tuple[str, ...] = ()
    errors: tuple[CollectionRefreshError, ...] = ()


@dataclass(frozen=True)
class _DatedMember:
    member_id: str
    start: date
    end: date
    private: bool
    # Whether this member is itself a date-derived smart collection, which
    # includes back any dated collection its range contains.
    date_derived: bool = False


def _collection_range(col: ExistingCollection) -> DateRange | None:
    parsed = parse_collection_name(col.name)
    return date_range(parsed.date) if parsed.date is not None else None


def _is_date_derived(col: ExistingCollection) -> bool:
    """Whether *col*'s members are materialized from its date range."""
    return (
        col.metadata.members == CollectionMembers.SMART
        and col.metadata.strategy != CollectionStrategy.ALBUM_SERIES
        and _collection_range(col) is not None
    )


def _smart_metadata(
    col: ExistingCollection,
    albums: tuple[_DatedMember, ...],
    collections: tuple[_DatedMember, ...],
) -> CollectionMetadata | None:
    """
    Return the members a date-range smart collection should have, or ``None``.

    ``None`` for collections whose members are not date-derived: manual ones,
    album-series ones (owned by the implicit refresh), and undated ones.
    Private smart collections only include private members; non-private ones
    exclude private members.

    A date-derived smart collection with the same range is left out: it
    would include this collection back, and the two would contain each
    other, a cycle the browsable tree cannot render.
    """
    col_range = _collection_range(col)
    if not _is_date_derived(col) or col_range is None:
        return None
    private = parse_collection_name(col.name).private

    def contained(members: tuple[_DatedMember, ...]) -> list[str]:
        return sorted(
            m.member_id
            for m in members
            if m.member_id != col.metadata.id
            and m.private == private
            and range_contains(col_range, (m.start, m.end))
            and not (m.date_derived and (m.start, m.end) == col_range)
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
) -> SmartChanges:
    """
    Materialize members for smart collections by date range.

    Returns the names of the updated collections; a save that fails stops the
    stage, and the collections saved before it are still returned.
    """
    dated_albums = tuple(
        _DatedMember(album.album_id, *rng, album.parsed.private)
        for album in albums
        for rng in [date_range(album.parsed.date)]
        if rng is not None
    )
    dated_collections = tuple(
        _DatedMember(
            col.metadata.id,
            *rng,
            private=parse_collection_name(col.name).private,
            date_derived=_is_date_derived(col),
        )
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
    return (
        SmartChanges(updated=tuple(col.name for col, _ in changed))
        if dry_run
        else _save_changed(changed)
    )


def _save_changed(
    changed: list[tuple[ExistingCollection, CollectionMetadata]],
) -> SmartChanges:
    """Save each changed collection, stopping at the first save that fails."""
    # Documented exception (docs/guidelines.md): per-item try/except, recording
    # the collections saved before a failure.
    saved: list[str] = []
    for col, new_meta in changed:
        try:
            save_collection_metadata(col.path, new_meta)
        except OSError as exc:
            return SmartChanges(updated=tuple(saved), errors=(filesystem_error(exc),))
        saved.append(col.name)
    return SmartChanges(updated=tuple(saved))
