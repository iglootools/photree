"""Sync album names with collection lifecycles (refresh phase 2).

An explicit collection owns its grouping, so the series is stripped from its
albums' names; an implicit collection's title is added as the series of its
series-less albums.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from ...album.naming import (
    ParsedAlbumName,
    reconstruct_name,
)
from ..naming import (
    parse_collection_name,
)
from ..store.protocol import (
    CollectionLifecycle,
)
from .result import (
    CollectionRefreshError,
    CollectionRefreshErrorKind,
)
from .scan import AlbumInfo, ExistingCollection


@dataclass(frozen=True)
class TitleSync:
    albums: tuple[AlbumInfo, ...]
    """Albums as they are after the sync (renames applied, even on dry run)."""

    renames: tuple[tuple[str, str], ...] = ()
    errors: tuple[CollectionRefreshError, ...] = ()


def _synced_title(
    album: AlbumInfo,
    explicit_titles: frozenset[str],
    implicit_by_album: Mapping[str, ExistingCollection],
) -> ParsedAlbumName:
    """The album name the collection lifecycles call for.

    - Explicit collection owns the album's series → strip it from the name.
    - Implicit collection contains a series-less album → add its title.
    """
    match album.parsed.series, implicit_by_album.get(album.album_id):
        case str() as series, _ if series in explicit_titles:
            return replace(album.parsed, series=None)
        case None, ExistingCollection() as col:
            return replace(album.parsed, series=parse_collection_name(col.name).title)
        case _:
            return album.parsed


def _plan_title_sync(
    albums: tuple[AlbumInfo, ...],
    existing: tuple[ExistingCollection, ...],
) -> list[tuple[AlbumInfo, AlbumInfo]]:
    """Pair each album whose name must change with its renamed self."""
    explicit_titles = frozenset(
        parse_collection_name(col.name).title
        for col in existing
        if col.metadata.lifecycle == CollectionLifecycle.EXPLICIT
    )
    implicit_by_album = {
        album_id: col
        for col in existing
        if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
        for album_id in col.metadata.albums
    }
    return [
        (album, replace(album, path=album.path.parent / new_name, parsed=new_parsed))
        for album in albums
        for new_parsed in [_synced_title(album, explicit_titles, implicit_by_album)]
        for new_name in [reconstruct_name(new_parsed)]
        if new_name != album.path.name
    ]


def _rename_conflicts(
    plan: list[tuple[AlbumInfo, AlbumInfo]],
) -> tuple[CollectionRefreshError, ...]:
    """Renames whose target is taken on disk or by another planned rename."""
    targets = [new.path for _, new in plan]
    return tuple(
        CollectionRefreshError(
            CollectionRefreshErrorKind.ALBUM_RENAME_CONFLICT,
            path=old.path,
            target=new.path,
        )
        for old, new in plan
        if new.path.exists() or targets.count(new.path) > 1
    )


def sync_album_titles(
    albums: tuple[AlbumInfo, ...],
    existing: tuple[ExistingCollection, ...],
    *,
    dry_run: bool,
) -> TitleSync:
    """Sync album titles with collection lifecycle changes.

    Returns the albums with their post-sync names, so later stages see the
    same names in a dry run as in a real one.
    """
    plan = _plan_title_sync(albums, existing)
    conflicts = _rename_conflicts(plan)
    if conflicts:
        return TitleSync(albums=albums, errors=conflicts)
    if not dry_run:
        for old, new in plan:
            old.path.rename(new.path)
    renamed = {old.path: new for old, new in plan}
    return TitleSync(
        albums=tuple(renamed.get(a.path, a) for a in albums),
        renames=tuple((old.path.name, new.path.name) for old, new in plan),
    )
