"""
Sync album names with collection lifecycles (refresh phase 2).

An explicit collection owns its grouping, so its title is stripped from the
series of its member albums. An implicit collection just converted from
explicit gets its title added back as the series of its series-less members;
once any member carries the series again, a member without it is one the user
took out of the series, and phase 3 drops it from the collection.
"""

from dataclasses import dataclass, replace

from photree.album.naming import ParsedAlbumName, reconstruct_name
from photree.collection.naming import parse_collection_name
from photree.collection.refresh.result import (
    CollectionRefreshError,
    CollectionRefreshErrorKind,
    filesystem_error,
)
from photree.collection.refresh.scan import AlbumInfo, ExistingCollection
from photree.collection.store.protocol import CollectionLifecycle


@dataclass(frozen=True)
class TitleSync:
    """The albums after syncing their series titles, the renames made and the errors."""

    albums: tuple[AlbumInfo, ...]
    """Albums as they are after the sync (renames applied, even on dry run)."""

    renames: tuple[tuple[str, str], ...] = ()
    errors: tuple[CollectionRefreshError, ...] = ()


def _title(col: ExistingCollection) -> str:
    return parse_collection_name(col.name).title


def _synced_title(
    album: AlbumInfo,
    explicit_titles: frozenset[str],
    converted_title: str | None,
) -> ParsedAlbumName:
    """
    Return the album name the collection lifecycles call for.

    - An explicit collection holding the album has its series as title →
      strip it from the name.
    - A just-converted implicit collection holds a series-less album → add
      its title.
    """
    match album.parsed.series, converted_title:
        case str() as series, _ if series in explicit_titles:
            return replace(album.parsed, series=None)
        case None, str() as title:
            return replace(album.parsed, series=title)
        case _:
            return album.parsed


def _explicit_titles_by_album(
    existing: tuple[ExistingCollection, ...],
) -> dict[str, frozenset[str]]:
    """Map each album ID to the titles of the explicit collections holding it."""
    explicit = [
        col
        for col in existing
        if col.metadata.lifecycle == CollectionLifecycle.EXPLICIT
    ]
    return {
        album_id: frozenset(
            _title(col) for col in explicit if album_id in col.metadata.albums
        )
        for album_id in {a for col in explicit for a in col.metadata.albums}
    }


def _converted_titles_by_album(
    albums: tuple[AlbumInfo, ...],
    existing: tuple[ExistingCollection, ...],
) -> dict[str, str]:
    """
    Map each member of a just-converted implicit collection to its title.

    An implicit collection counts as just converted from explicit when none of
    its members carries its title as their series: the explicit collection had
    them stripped. Phase 3 writes the series into every member's name, so once
    one member carries it, a member without it was taken out by the user.
    """
    series_by_id = {album.album_id: album.parsed.series for album in albums}
    return {
        album_id: title
        for col in existing
        if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
        for title in [_title(col)]
        if not any(series_by_id.get(a) == title for a in col.metadata.albums)
        for album_id in col.metadata.albums
    }


def _plan_title_sync(
    albums: tuple[AlbumInfo, ...],
    existing: tuple[ExistingCollection, ...],
) -> list[tuple[AlbumInfo, AlbumInfo]]:
    """Pair each album whose name must change with its renamed self."""
    explicit_titles = _explicit_titles_by_album(existing)
    converted_titles = _converted_titles_by_album(albums, existing)
    return [
        (album, replace(album, path=album.path.parent / new_name, parsed=new_parsed))
        for album in albums
        for new_parsed in [
            _synced_title(
                album,
                explicit_titles.get(album.album_id, frozenset()),
                converted_titles.get(album.album_id),
            ),
        ]
        for new_name in [reconstruct_name(new_parsed)]
        if new_name != album.path.name
    ]


def _rename_conflicts(
    plan: list[tuple[AlbumInfo, AlbumInfo]],
) -> tuple[CollectionRefreshError, ...]:
    """Return the renames whose target is taken on disk or by another planned rename."""
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
    """
    Sync album titles with collection lifecycle changes.

    Returns the albums with their post-sync names, so later stages see the
    same names in a dry run as in a real one.
    """
    plan = _plan_title_sync(albums, existing)
    conflicts = _rename_conflicts(plan)
    if conflicts:
        return TitleSync(albums=albums, errors=conflicts)
    applied, error = (plan, None) if dry_run else _apply_renames(plan)
    renamed = {old.path: new for old, new in applied}
    return TitleSync(
        albums=tuple(renamed.get(a.path, a) for a in albums),
        renames=tuple((old.path.name, new.path.name) for old, new in applied),
        errors=(error,) if error is not None else (),
    )


def _apply_renames(
    plan: list[tuple[AlbumInfo, AlbumInfo]],
) -> tuple[list[tuple[AlbumInfo, AlbumInfo]], CollectionRefreshError | None]:
    """
    Rename the albums of *plan* in order, stopping at the first that fails.

    Returns the renames done and the failure, so a refresh that stops part-way
    still reports the albums it already renamed.
    """
    # Documented exception (docs/guidelines.md): per-item try/except, recording
    # the renames done before a failure.
    done: list[tuple[AlbumInfo, AlbumInfo]] = []
    for old, new in plan:
        try:
            old.path.rename(new.path)
        except OSError as exc:
            return done, filesystem_error(exc)
        done.append((old, new))
    return done, None
