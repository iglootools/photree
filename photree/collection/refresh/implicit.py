"""Create, update, rename and delete implicit collections (refresh phase 3)."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from photree.collection.naming import parse_collection_year
from photree.collection.refresh.implicit_match import (
    GroupMatch,
    ImplicitIndex,
    match_groups,
)
from photree.collection.refresh.result import (
    CollectionRefreshError,
    CollectionRefreshErrorKind,
)
from photree.collection.refresh.scan import AlbumInfo, ExistingCollection
from photree.collection.refresh.series import SeriesTarget, series_targets
from photree.collection.store.metadata import (
    remove_collection_metadata,
    save_collection_metadata,
)
from photree.collection.store.protocol import (
    COLLECTION_YAML,
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from photree.foundation.layout import COLLECTIONS_DIR, PHOTREE_DIR

_FINDER_METADATA = ".DS_Store"


def _collection_target_dir(gallery_dir: Path, name: str) -> Path:
    match parse_collection_year(name):
        case None:
            return gallery_dir / COLLECTIONS_DIR / name
        case year:
            return gallery_dir / COLLECTIONS_DIR / year / name


@dataclass(frozen=True)
class ImplicitChanges:
    """The implicit collections a refresh created, updated, renamed or deleted."""

    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()
    deleted: tuple[str, ...] = ()
    kept_directories: tuple[str, ...] = ()
    """Deleted collections whose directory was kept: it holds other files."""
    errors: tuple[CollectionRefreshError, ...] = ()
    collections: tuple[ExistingCollection, ...] = ()
    """Every collection in the gallery as the stage leaves it, even on dry run."""


def _implicit_metadata(
    base: CollectionMetadata,
    album_ids: tuple[str, ...],
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


@dataclass(frozen=True)
class _Update:
    """An existing implicit collection, renamed (date range or title) and/or updated."""

    col: ExistingCollection
    name: str
    path: Path
    metadata: CollectionMetadata

    @property
    def moves(self) -> bool:
        """Whether the collection directory changes."""
        return self.path != self.col.path


@dataclass(frozen=True)
class _Create:
    """A new implicit collection for a series run no existing one matches."""

    name: str
    path: Path
    metadata: CollectionMetadata


@dataclass(frozen=True)
class _Orphan:
    """An implicit collection no album series backs any more."""

    col: ExistingCollection
    empties: bool
    """Removing its metadata leaves the directory empty, so it is removed too."""


def _names(directory: Path) -> set[str]:
    return {child.name for child in directory.iterdir()}


def _plan_orphan(col: ExistingCollection) -> _Orphan:
    """
    Plan the removal of *col*'s metadata, and of its directory if nothing else is in it.

    Finder's ``.DS_Store`` does not count: browsing the directory creates it.
    """
    return _Orphan(
        col=col,
        empties=_names(col.path) <= {PHOTREE_DIR, _FINDER_METADATA}
        and _names(col.path / PHOTREE_DIR) == {COLLECTION_YAML},
    )


@dataclass(frozen=True)
class _ImplicitPlan:
    """Every change the implicit stage makes, computed before any is applied."""

    updates: tuple[_Update, ...]
    creates: tuple[_Create, ...]
    orphans: tuple[_Orphan, ...]


def _plan_update(
    gallery_dir: Path,
    col: ExistingCollection,
    target: SeriesTarget,
) -> _Update:
    return _Update(
        col=col,
        name=target.collection_name,
        path=_collection_target_dir(gallery_dir, target.collection_name),
        metadata=_implicit_metadata(col.metadata, target.album_ids),
    )


def _plan_create(
    gallery_dir: Path,
    target: SeriesTarget,
    new_id: Callable[[], str],
) -> _Create:
    return _Create(
        name=target.collection_name,
        path=_collection_target_dir(gallery_dir, target.collection_name),
        metadata=CollectionMetadata(
            id=new_id(),
            members=CollectionMembers.SMART,
            lifecycle=CollectionLifecycle.IMPLICIT,
            strategy=CollectionStrategy.ALBUM_SERIES,
            albums=list(target.album_ids),
        ),
    )


def _plan(
    gallery_dir: Path,
    index: ImplicitIndex,
    matches: list[GroupMatch],
    new_id: Callable[[], str],
) -> _ImplicitPlan:
    kept = {m.existing.metadata.id for m in matches if m.existing is not None}
    return _ImplicitPlan(
        updates=tuple(
            _plan_update(gallery_dir, m.existing, m.target)
            for m in matches
            if m.existing is not None
        ),
        creates=tuple(
            _plan_create(gallery_dir, m.target, new_id)
            for m in matches
            if m.existing is None
        ),
        orphans=tuple(
            _plan_orphan(col) for col in index.implicit if col.metadata.id not in kept
        ),
    )


def _vacated(plan: _ImplicitPlan) -> tuple[Path, ...]:
    """Return the collection directories the plan moves away or removes."""
    return (
        *(u.col.path for u in plan.updates if u.moves),
        *(o.col.path for o in plan.orphans if o.empties),
    )


def _is_taken(target: Path, vacated: tuple[Path, ...]) -> bool:
    """
    Whether *target* is occupied by something the plan does not vacate.

    Compared with ``samefile`` so that, on a case-insensitive filesystem, a
    case-only rename does not find the collection itself in its way.
    """
    return target.exists() and not any(
        v.exists() and target.samefile(v) for v in vacated
    )


def _target_errors(plan: _ImplicitPlan) -> tuple[CollectionRefreshError, ...]:
    vacated = _vacated(plan)
    return (
        *(
            CollectionRefreshError(
                CollectionRefreshErrorKind.COLLECTION_TARGET_EXISTS,
                path=u.col.path,
                target=u.path,
            )
            for u in plan.updates
            if u.moves and _is_taken(u.path, vacated)
        ),
        *(
            CollectionRefreshError(
                CollectionRefreshErrorKind.COLLECTION_TARGET_EXISTS,
                target=c.path,
            )
            for c in plan.creates
            if _is_taken(c.path, vacated)
        ),
    )


def _apply(plan: _ImplicitPlan) -> None:
    """
    Write *plan* to disk: removals, then moves, then metadata and creations.

    An orphan loses only its metadata; its directory goes too only when that
    leaves it empty, so files the user keeps there survive.

    Moves go through a temporary name first, so a case-only rename and one
    collection taking another's vacated name both work.
    """
    for orphan in plan.orphans:
        remove_collection_metadata(orphan.col.path)
        if orphan.empties:
            (orphan.col.path / _FINDER_METADATA).unlink(missing_ok=True)
            orphan.col.path.rmdir()
    staged = [
        (u, u.col.path.with_name(f".photree-moving-{u.metadata.id}"))
        for u in plan.updates
        if u.moves
    ]
    for u, temporary in staged:
        u.col.path.rename(temporary)
    for u, temporary in staged:
        u.path.parent.mkdir(parents=True, exist_ok=True)
        temporary.rename(u.path)
    for u in plan.updates:
        if u.metadata != u.col.metadata:
            save_collection_metadata(u.path, u.metadata)
    for c in plan.creates:
        c.path.mkdir(parents=True)
        save_collection_metadata(c.path, c.metadata)


def _planned_collections(
    existing: tuple[ExistingCollection, ...],
    plan: _ImplicitPlan,
) -> tuple[ExistingCollection, ...]:
    """Return *existing* with the plan's renames, updates, creations and removals."""
    updated = {
        u.col.metadata.id: ExistingCollection(u.path, u.metadata, u.name)
        for u in plan.updates
    }
    removed = {o.col.metadata.id for o in plan.orphans}
    return (
        *(
            updated.get(col.metadata.id, col)
            for col in existing
            if col.metadata.id not in removed
        ),
        *(ExistingCollection(c.path, c.metadata, c.name) for c in plan.creates),
    )


def _changes(
    existing: tuple[ExistingCollection, ...],
    plan: _ImplicitPlan,
) -> ImplicitChanges:
    return ImplicitChanges(
        created=tuple(c.name for c in plan.creates),
        updated=tuple(u.name for u in plan.updates if u.metadata != u.col.metadata),
        renamed=tuple(
            (u.col.name, u.name) for u in plan.updates if u.col.name != u.name
        ),
        deleted=tuple(o.col.name for o in plan.orphans),
        kept_directories=tuple(o.col.name for o in plan.orphans if not o.empties),
        collections=_planned_collections(existing, plan),
    )


def refresh_implicit_collections(
    gallery_dir: Path,
    albums: tuple[AlbumInfo, ...],
    existing: tuple[ExistingCollection, ...],
    *,
    dry_run: bool,
    new_id: Callable[[], str],
) -> ImplicitChanges:
    """
    Create, update, rename, and delete implicit collections from album series.

    Nothing is written when the plan has an error: series name conflicts and
    occupied target directories are detected on the whole plan first, taking
    into account the directories the plan itself moves away or removes.
    """
    index = ImplicitIndex.build(existing)
    matches = match_groups(series_targets(albums), index)
    conflicts = tuple(
        CollectionRefreshError(
            CollectionRefreshErrorKind.SERIES_NAME_CONFLICT,
            name=m.target.collection_name,
        )
        for m in matches
        if m.conflict
    )
    if conflicts:
        return ImplicitChanges(errors=conflicts)
    plan = _plan(gallery_dir, index, matches, new_id)
    target_errors = _target_errors(plan)
    if target_errors:
        return ImplicitChanges(errors=target_errors)
    if not dry_run:
        _apply(plan)
    return _changes(existing, plan)
