"""Refresh implicit collections and smart collection members.

Called by ``gallery refresh`` to:
1. Detect album series → create/update/rename/delete implicit collections
2. Materialize smart collection members by date range
3. Sync album titles with collection lifecycle changes

Each stage plans its changes first and validates them (target names free,
no two groups claiming one name) before touching the filesystem, so a
refresh that reports an error has not half-applied its stage. Dry runs
follow the same plan, applied in memory only.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from pathlib import Path

from ..album.naming import (
    NamingIssue,
    ParsedAlbumName,
    check_album_naming,
    check_batch_date_collisions,
    parse_album_name,
    reconstruct_name,
)
from ..album.store.album_discovery import discover_albums
from ..album.store.metadata import load_album_metadata
from ..album.store.protocol import AlbumMetadata
from ..collection.id import generate_collection_id
from ..collection.naming import (
    parse_collection_name,
    parse_collection_year,
    reconstruct_collection_name,
)
from ..collection.store.collection_discovery import discover_collections
from ..collection.store.metadata import (
    load_collection_metadata,
    save_collection_metadata,
)
from ..collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from ..dates import DateRange, date_range, range_contains
from ..foundation.layout import ALBUMS_DIR, COLLECTIONS_DIR
from .metadata_scan import read_or_none

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class CollectionRefreshErrorKind(StrEnum):
    """Why a collection refresh stopped."""

    ALBUM_NAMING = "album-naming"
    """``path``: album whose name breaks the convention (``naming_issues``)."""

    ALBUM_MISSING_METADATA = "album-missing-metadata"
    """``path``: album without a readable ``.photree/album.yaml``."""

    COLLECTION_UNREADABLE_METADATA = "collection-unreadable-metadata"
    """``path``: collection whose ``collection.yaml`` cannot be read."""

    DATE_COLLISION = "date-collision"
    """``name``: the date; ``album_names``: the colliding albums."""

    ALBUM_RENAME_CONFLICT = "album-rename-conflict"
    """``path``: album; ``target``: title-sync name already taken."""

    COLLECTION_TARGET_EXISTS = "collection-target-exists"
    """``path``: collection being renamed (``None`` on create); ``target``."""

    SERIES_NAME_CONFLICT = "series-name-conflict"
    """``name``: implicit collection name claimed by two album series runs."""


@dataclass(frozen=True)
class CollectionRefreshError:
    """An error encountered during collection refresh.

    Which fields are set depends on :attr:`kind` (see
    :class:`CollectionRefreshErrorKind`). Paths are absolute; the CLI renders
    them relative to the working directory.
    """

    kind: CollectionRefreshErrorKind
    path: Path | None = None
    target: Path | None = None
    name: str | None = None
    naming_issues: tuple[NamingIssue, ...] = ()
    album_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionRefreshResult:
    """Result of a collection refresh run."""

    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()  # (old_name, new_name)
    deleted: tuple[str, ...] = ()
    album_renames: tuple[tuple[str, str], ...] = ()  # (old_name, new_name)
    errors: tuple[CollectionRefreshError, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AlbumInfo:
    """Parsed album info needed for collection refresh."""

    path: Path
    album_id: str
    parsed: ParsedAlbumName


@dataclass(frozen=True)
class _ExistingCollection:
    """An existing collection on disk."""

    path: Path
    metadata: CollectionMetadata
    name: str


@dataclass(frozen=True)
class _Scan:
    albums: tuple[_AlbumInfo, ...]
    collections: tuple[_ExistingCollection, ...]
    errors: tuple[CollectionRefreshError, ...]


def _try_scan_album(album_dir: Path) -> _AlbumInfo | CollectionRefreshError:
    """Validate and scan a single album. Returns info or error."""
    issues = check_album_naming(album_dir.name)
    parsed = parse_album_name(album_dir.name)
    meta = read_or_none(load_album_metadata, album_dir)
    match (issues, parsed, meta):
        case ((), ParsedAlbumName() as valid, AlbumMetadata() as valid_meta):
            return _AlbumInfo(path=album_dir, album_id=valid_meta.id, parsed=valid)
        case ((), ParsedAlbumName(), None):
            return CollectionRefreshError(
                CollectionRefreshErrorKind.ALBUM_MISSING_METADATA, path=album_dir
            )
        case _:
            return CollectionRefreshError(
                CollectionRefreshErrorKind.ALBUM_NAMING,
                path=album_dir,
                naming_issues=issues,
            )


def _try_scan_collection(col_dir: Path) -> _ExistingCollection | CollectionRefreshError:
    meta = read_or_none(load_collection_metadata, col_dir)
    return (
        _ExistingCollection(path=col_dir, metadata=meta, name=col_dir.name)
        if meta is not None
        else CollectionRefreshError(
            CollectionRefreshErrorKind.COLLECTION_UNREADABLE_METADATA, path=col_dir
        )
    )


def _scan_existing_collections(
    gallery_dir: Path,
) -> tuple[tuple[_ExistingCollection, ...], tuple[CollectionRefreshError, ...]]:
    """Find all existing collections in the gallery."""
    results = [
        _try_scan_collection(d)
        for d in discover_collections(gallery_dir / COLLECTIONS_DIR)
    ]
    return (
        tuple(r for r in results if isinstance(r, _ExistingCollection)),
        tuple(r for r in results if isinstance(r, CollectionRefreshError)),
    )


def _date_collision_errors(
    albums: tuple[_AlbumInfo, ...],
) -> tuple[CollectionRefreshError, ...]:
    batch = check_batch_date_collisions([(a.path.name, a.parsed) for a in albums])
    return tuple(
        CollectionRefreshError(
            CollectionRefreshErrorKind.DATE_COLLISION,
            name=album_date,
            album_names=names,
        )
        for album_date, names in batch.date_collisions
    )


def _scan_gallery(gallery_dir: Path) -> _Scan:
    """Scan albums and collections; collect every reason to stop.

    Collisions are only checked once every name parses, since an
    unparseable name has no date to collide on.
    """
    album_results = [
        _try_scan_album(d) for d in discover_albums(gallery_dir / ALBUMS_DIR)
    ]
    albums = tuple(r for r in album_results if isinstance(r, _AlbumInfo))
    album_errors = tuple(
        r for r in album_results if isinstance(r, CollectionRefreshError)
    )
    collections, collection_errors = _scan_existing_collections(gallery_dir)
    return _Scan(
        albums=albums,
        collections=collections,
        errors=(
            *album_errors,
            *collection_errors,
            *(() if album_errors else _date_collision_errors(albums)),
        ),
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _compute_date_string(dates: list[str]) -> str:
    """Compute a date string that covers all given album dates.

    Same date → that date. Different dates → min-max range.
    """
    ranges = [rng for d in dates for rng in [date_range(d)] if rng is not None]
    match dates, ranges:
        case [], _:
            return ""
        case [single], _:
            return single
        case [first, *_], []:
            return first
        case _:
            min_start = min(s for s, _ in ranges)
            max_end = max(e for _, e in ranges)
            return str(min_start) if min_start == max_end else f"{min_start}--{max_end}"


def _collection_target_dir(gallery_dir: Path, name: str) -> Path:
    """Compute the target directory for a collection."""
    match parse_collection_year(name):
        case None:
            return gallery_dir / COLLECTIONS_DIR / name
        case year:
            return gallery_dir / COLLECTIONS_DIR / year / name


def _build_collection_name(series_title: str, album_dates: list[str]) -> str:
    """Build the canonical collection name for a series."""
    date_str = _compute_date_string(album_dates)
    raw_name = f"{date_str} - {series_title}" if date_str else series_title
    return reconstruct_collection_name(parse_collection_name(raw_name))


@dataclass(frozen=True)
class _SeriesGroup:
    """A contiguous run of albums sharing the same series."""

    series_title: str
    albums: tuple[_AlbumInfo, ...]


def _group_contiguous_series(albums: Iterable[_AlbumInfo]) -> list[_SeriesGroup]:
    """Group albums into contiguous runs of the same series.

    Albums are sorted by name (chronological, since names start with dates).
    A series interrupted by albums without that series (or with a different
    series) produces separate groups. The same series title appearing in
    non-contiguous positions results in multiple groups.
    """
    sorted_albums = sorted(albums, key=lambda a: a.path.name)

    groups: list[_SeriesGroup] = []
    current_series: str | None = None
    current_run: list[_AlbumInfo] = []

    for album in sorted_albums:
        if album.parsed.series is not None and album.parsed.series == current_series:
            # Continue the current run
            current_run.append(album)
        else:
            # Flush previous run
            if current_series is not None and current_run:
                groups.append(
                    _SeriesGroup(series_title=current_series, albums=tuple(current_run))
                )
            # Start new run (or reset if no series)
            if album.parsed.series is not None:
                current_series = album.parsed.series
                current_run = [album]
            else:
                current_series = None
                current_run = []

    # Flush final run
    if current_series is not None and current_run:
        groups.append(
            _SeriesGroup(series_title=current_series, albums=tuple(current_run))
        )

    return groups


# ---------------------------------------------------------------------------
# Album title sync
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TitleSync:
    albums: tuple[_AlbumInfo, ...]
    """Albums as they are after the sync (renames applied, even on dry run)."""

    renames: tuple[tuple[str, str], ...] = ()
    errors: tuple[CollectionRefreshError, ...] = ()


def _synced_title(
    album: _AlbumInfo,
    explicit_titles: frozenset[str],
    implicit_by_album: Mapping[str, _ExistingCollection],
) -> ParsedAlbumName:
    """The album name the collection lifecycles call for.

    - Explicit collection owns the album's series → strip it from the name.
    - Implicit collection contains a series-less album → add its title.
    """
    match album.parsed.series, implicit_by_album.get(album.album_id):
        case str() as series, _ if series in explicit_titles:
            return replace(album.parsed, series=None)
        case None, _ExistingCollection() as col:
            return replace(album.parsed, series=parse_collection_name(col.name).title)
        case _:
            return album.parsed


def _plan_title_sync(
    albums: tuple[_AlbumInfo, ...],
    existing: tuple[_ExistingCollection, ...],
) -> list[tuple[_AlbumInfo, _AlbumInfo]]:
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
    plan: list[tuple[_AlbumInfo, _AlbumInfo]],
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


def _sync_album_titles(
    albums: tuple[_AlbumInfo, ...],
    existing: tuple[_ExistingCollection, ...],
    *,
    dry_run: bool,
) -> _TitleSync:
    """Sync album titles with collection lifecycle changes.

    Returns the albums with their post-sync names, so later stages see the
    same names in a dry run as in a real one.
    """
    plan = _plan_title_sync(albums, existing)
    conflicts = _rename_conflicts(plan)
    if conflicts:
        return _TitleSync(albums=albums, errors=conflicts)
    if not dry_run:
        for old, new in plan:
            old.path.rename(new.path)
    renamed = {old.path: new for old, new in plan}
    return _TitleSync(
        albums=tuple(renamed.get(a.path, a) for a in albums),
        renames=tuple((old.path.name, new.path.name) for old, new in plan),
    )


# ---------------------------------------------------------------------------
# Implicit collections: matching series groups to existing collections
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SeriesTarget:
    """What one series group's implicit collection should look like."""

    series_title: str
    collection_name: str
    album_ids: tuple[str, ...]


@dataclass(frozen=True)
class _ImplicitIndex:
    """Lookup structures for matching series groups to existing implicit collections."""

    implicit: tuple[_ExistingCollection, ...]
    by_name: Mapping[str, _ExistingCollection]
    by_title: Mapping[str, tuple[_ExistingCollection, ...]]

    @staticmethod
    def build(existing: tuple[_ExistingCollection, ...]) -> _ImplicitIndex:
        implicit = tuple(
            col
            for col in existing
            if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
        )
        titled = [(parse_collection_name(col.name).title, col) for col in implicit]
        return _ImplicitIndex(
            implicit=implicit,
            by_name={col.name: col for col in implicit},
            by_title={
                title: tuple(col for t, col in titled if t == title)
                for title in dict.fromkeys(t for t, _ in titled)
            },
        )


def _series_targets(albums: tuple[_AlbumInfo, ...]) -> list[_SeriesTarget]:
    """One target per contiguous series run; private albums never join one."""
    return [
        _SeriesTarget(
            series_title=group.series_title,
            collection_name=_build_collection_name(
                group.series_title, [a.parsed.date for a in public]
            ),
            album_ids=tuple(sorted(a.album_id for a in public)),
        )
        for group in _group_contiguous_series(albums)
        for public in [[a for a in group.albums if not a.parsed.private]]
        if public
    ]


def _find_by_title_overlap(
    candidates: tuple[_ExistingCollection, ...],
    active_ids: frozenset[str],
    album_ids: tuple[str, ...],
) -> _ExistingCollection | None:
    """Find an implicit collection with the same title that shares members.

    Used when the date range changed (albums added/removed) but the series
    title is the same. Prefers the candidate with the most overlap (the first
    one on a tie).
    """
    album_set = set(album_ids)
    best = max(
        (
            (len(album_set & set(col.metadata.albums)), col)
            for col in candidates
            if col.metadata.id not in active_ids
        ),
        key=lambda scored: scored[0],
        default=None,
    )
    return best[1] if best is not None and best[0] > 0 else None


def _find_renamed_implicit(
    implicit: tuple[_ExistingCollection, ...],
    active_ids: frozenset[str],
    album_ids: tuple[str, ...],
) -> _ExistingCollection | None:
    """Find an implicit collection whose members match (rename detection)."""
    album_set = set(album_ids)
    return next(
        (
            col
            for col in implicit
            if col.metadata.id not in active_ids
            and set(col.metadata.albums) == album_set
        ),
        None,
    )


def _match_existing(
    target: _SeriesTarget, index: _ImplicitIndex, active_ids: frozenset[str]
) -> _ExistingCollection | None:
    """Match a target to an existing implicit collection not yet claimed.

    1. Exact name match. 2. Same title, overlapping members (date range
    changed). 3. Identical members (series title changed).
    """
    by_name = index.by_name.get(target.collection_name)
    return (
        (
            by_name
            if by_name is not None and by_name.metadata.id not in active_ids
            else None
        )
        or _find_by_title_overlap(
            index.by_title.get(target.series_title, ()), active_ids, target.album_ids
        )
        or _find_renamed_implicit(index.implicit, active_ids, target.album_ids)
    )


@dataclass(frozen=True)
class _GroupMatch:
    target: _SeriesTarget
    existing: _ExistingCollection | None
    conflict: bool = False
    """Another, earlier series run already claimed this collection name."""


def _match_groups(
    targets: list[_SeriesTarget], index: _ImplicitIndex
) -> list[_GroupMatch]:
    """Match every target, each existing collection at most once.

    A documented accumulator exception (loop-carried state): which IDs and
    names are already claimed depends on every earlier match, so the loop
    threads them through. Without it, two same-date runs of one series
    (A, B, A) build the same name and the second silently overwrites the
    first's collection.
    """
    matches: list[_GroupMatch] = []
    claimed_ids: frozenset[str] = frozenset()
    claimed_names: frozenset[str] = frozenset()
    for target in targets:
        group_match = (
            _GroupMatch(target, None, conflict=True)
            if target.collection_name in claimed_names
            else _GroupMatch(target, _match_existing(target, index, claimed_ids))
        )
        claimed_names |= {target.collection_name}
        if group_match.existing is not None:
            claimed_ids |= {group_match.existing.metadata.id}
        matches.append(group_match)
    return matches


# ---------------------------------------------------------------------------
# Implicit collections: applying matches
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ImplicitChanges:
    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()
    deleted: tuple[str, ...] = ()
    errors: tuple[CollectionRefreshError, ...] = ()

    @staticmethod
    def merge(changes: Iterable[_ImplicitChanges]) -> _ImplicitChanges:
        all_changes = list(changes)
        return _ImplicitChanges(
            created=tuple(n for c in all_changes for n in c.created),
            updated=tuple(n for c in all_changes for n in c.updated),
            renamed=tuple(r for c in all_changes for r in c.renamed),
            deleted=tuple(n for c in all_changes for n in c.deleted),
            errors=tuple(e for c in all_changes for e in c.errors),
        )


def _implicit_metadata(
    base: CollectionMetadata, album_ids: tuple[str, ...]
) -> CollectionMetadata:
    return CollectionMetadata(
        id=base.id,
        members=base.members,
        lifecycle=CollectionLifecycle.IMPLICIT,
        strategy=CollectionStrategy.ALBUM_SERIES,
        albums=list(album_ids),
        collections=base.collections,
        images=base.images,
        videos=base.videos,
    )


def _update_existing(
    gallery_dir: Path,
    col: _ExistingCollection,
    target: _SeriesTarget,
    *,
    dry_run: bool,
) -> _ImplicitChanges:
    """Rename (date range or title changed) and/or update members, keeping the ID."""
    new_path = _collection_target_dir(gallery_dir, target.collection_name)
    if new_path != col.path and new_path.exists():
        return _ImplicitChanges(
            errors=(
                CollectionRefreshError(
                    CollectionRefreshErrorKind.COLLECTION_TARGET_EXISTS,
                    path=col.path,
                    target=new_path,
                ),
            )
        )
    new_meta = _implicit_metadata(col.metadata, target.album_ids)
    if not dry_run and new_path != col.path:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        col.path.rename(new_path)
    if not dry_run and new_meta != col.metadata:
        save_collection_metadata(new_path, new_meta)
    return _ImplicitChanges(
        renamed=(
            ((col.name, target.collection_name),)
            if col.name != target.collection_name
            else ()
        ),
        updated=(target.collection_name,) if new_meta != col.metadata else (),
    )


def _create_implicit(
    gallery_dir: Path,
    target: _SeriesTarget,
    *,
    dry_run: bool,
    new_id: Callable[[], str],
) -> _ImplicitChanges:
    """Create a new implicit collection."""
    target_dir = _collection_target_dir(gallery_dir, target.collection_name)
    if target_dir.exists():
        return _ImplicitChanges(
            errors=(
                CollectionRefreshError(
                    CollectionRefreshErrorKind.COLLECTION_TARGET_EXISTS,
                    target=target_dir,
                ),
            )
        )
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
        save_collection_metadata(
            target_dir,
            CollectionMetadata(
                id=new_id(),
                members=CollectionMembers.SMART,
                lifecycle=CollectionLifecycle.IMPLICIT,
                strategy=CollectionStrategy.ALBUM_SERIES,
                albums=list(target.album_ids),
            ),
        )
    return _ImplicitChanges(created=(target.collection_name,))


def _apply_match(
    gallery_dir: Path,
    group_match: _GroupMatch,
    *,
    dry_run: bool,
    new_id: Callable[[], str],
) -> _ImplicitChanges:
    match group_match.existing:
        case _ExistingCollection() as col:
            return _update_existing(
                gallery_dir, col, group_match.target, dry_run=dry_run
            )
        case None:
            return _create_implicit(
                gallery_dir, group_match.target, dry_run=dry_run, new_id=new_id
            )


def _delete_orphaned_implicit(
    index: _ImplicitIndex,
    matches: list[_GroupMatch],
    *,
    dry_run: bool,
) -> _ImplicitChanges:
    """Delete implicit collections no longer backed by any album series."""
    kept = {m.existing.metadata.id for m in matches if m.existing is not None}
    orphans = [col for col in index.implicit if col.metadata.id not in kept]
    if not dry_run:
        for col in orphans:
            shutil.rmtree(col.path)
    return _ImplicitChanges(deleted=tuple(col.name for col in orphans))


def _refresh_implicit_collections(
    gallery_dir: Path,
    albums: tuple[_AlbumInfo, ...],
    existing: tuple[_ExistingCollection, ...],
    *,
    dry_run: bool,
    new_id: Callable[[], str],
) -> _ImplicitChanges:
    """Create, update, rename, and delete implicit collections from album series.

    Nothing is written when any group fails to match: name conflicts are
    detected on the whole plan first.
    """
    index = _ImplicitIndex.build(existing)
    matches = _match_groups(_series_targets(albums), index)
    conflicts = tuple(
        CollectionRefreshError(
            CollectionRefreshErrorKind.SERIES_NAME_CONFLICT,
            name=m.target.collection_name,
        )
        for m in matches
        if m.conflict
    )
    if conflicts:
        return _ImplicitChanges(errors=conflicts)
    return _ImplicitChanges.merge(
        [
            *(
                _apply_match(gallery_dir, m, dry_run=dry_run, new_id=new_id)
                for m in matches
            ),
            _delete_orphaned_implicit(index, matches, dry_run=dry_run),
        ]
    )


# ---------------------------------------------------------------------------
# Smart collection logic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DatedMember:
    member_id: str
    start: date
    end: date
    private: bool


def _collection_range(col: _ExistingCollection) -> DateRange | None:
    parsed = parse_collection_name(col.name)
    return date_range(parsed.date) if parsed.date is not None else None


def _smart_metadata(
    col: _ExistingCollection,
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


def _refresh_smart_collections(
    albums: tuple[_AlbumInfo, ...],
    all_collections: tuple[_ExistingCollection, ...],
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# Refresh stage names (for progress callbacks)
STAGE_SCAN_ALBUMS = "scan-albums"
STAGE_TITLE_SYNC = "title-sync"
STAGE_IMPLICIT_REFRESH = "implicit-refresh"
STAGE_SMART_REFRESH = "smart-refresh"

REFRESH_STAGES = (
    STAGE_SCAN_ALBUMS,
    STAGE_TITLE_SYNC,
    STAGE_IMPLICIT_REFRESH,
    STAGE_SMART_REFRESH,
)


@dataclass(frozen=True)
class _Notifier:
    on_stage_start: Callable[[str], None] | None
    on_stage_end: Callable[[str], None] | None

    @contextmanager
    def stage(self, name: str) -> Generator[None, None, None]:
        if self.on_stage_start is not None:
            self.on_stage_start(name)
        yield
        if self.on_stage_end is not None:
            self.on_stage_end(name)


def _partial_result(
    implicit: _ImplicitChanges, sync: _TitleSync
) -> CollectionRefreshResult:
    """The result as of the end of the implicit stage."""
    return CollectionRefreshResult(
        created=implicit.created,
        updated=implicit.updated,
        renamed=implicit.renamed,
        deleted=implicit.deleted,
        album_renames=sync.renames,
        errors=implicit.errors,
    )


def refresh_collections(
    gallery_dir: Path,
    *,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    new_id: Callable[[], str] = generate_collection_id,
) -> CollectionRefreshResult:
    """Refresh all collections in the gallery.

    1. Scan and validate album names (light check, no EXIF)
    2. Sync album titles with existing collection lifecycle changes
    3. Refresh implicit collections from album series
    4. Materialize smart collection members
    """
    notifier = _Notifier(on_stage_start, on_stage_end)
    with notifier.stage(STAGE_SCAN_ALBUMS):
        scan = _scan_gallery(gallery_dir)
    if scan.errors:
        return CollectionRefreshResult(errors=scan.errors)

    with notifier.stage(STAGE_TITLE_SYNC):
        sync = _sync_album_titles(scan.albums, scan.collections, dry_run=dry_run)
    if sync.errors:
        return CollectionRefreshResult(errors=sync.errors)

    with notifier.stage(STAGE_IMPLICIT_REFRESH):
        implicit = _refresh_implicit_collections(
            gallery_dir, sync.albums, scan.collections, dry_run=dry_run, new_id=new_id
        )
    partial = _partial_result(implicit, sync)
    if implicit.errors:
        return partial

    with notifier.stage(STAGE_SMART_REFRESH):
        # Re-scan: the implicit stage may have renamed or created collections.
        collections, rescan_errors = _scan_existing_collections(gallery_dir)
        smart_updated = _refresh_smart_collections(
            sync.albums, collections, dry_run=dry_run
        )
    return replace(
        partial,
        updated=(*partial.updated, *smart_updated),
        errors=rescan_errors,
    )
