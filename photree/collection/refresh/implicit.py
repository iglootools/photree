"""Create, update, rename and delete implicit collections (refresh phase 3)."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from ...foundation.layout import COLLECTIONS_DIR
from ..naming import (
    parse_collection_year,
)
from ..store.metadata import (
    save_collection_metadata,
)
from ..store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from .implicit_match import GroupMatch, ImplicitIndex, match_groups
from .result import (
    CollectionRefreshError,
    CollectionRefreshErrorKind,
)
from .scan import AlbumInfo, ExistingCollection
from .series import SeriesTarget, series_targets


def _collection_target_dir(gallery_dir: Path, name: str) -> Path:
    """Compute the target directory for a collection."""
    match parse_collection_year(name):
        case None:
            return gallery_dir / COLLECTIONS_DIR / name
        case year:
            return gallery_dir / COLLECTIONS_DIR / year / name


@dataclass(frozen=True)
class ImplicitChanges:
    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()
    deleted: tuple[str, ...] = ()
    errors: tuple[CollectionRefreshError, ...] = ()

    @staticmethod
    def merge(changes: Iterable[ImplicitChanges]) -> ImplicitChanges:
        all_changes = list(changes)
        return ImplicitChanges(
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
    col: ExistingCollection,
    target: SeriesTarget,
    *,
    dry_run: bool,
) -> ImplicitChanges:
    """Rename (date range or title changed) and/or update members, keeping the ID."""
    new_path = _collection_target_dir(gallery_dir, target.collection_name)
    if new_path != col.path and new_path.exists():
        return ImplicitChanges(
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
    return ImplicitChanges(
        renamed=(
            ((col.name, target.collection_name),)
            if col.name != target.collection_name
            else ()
        ),
        updated=(target.collection_name,) if new_meta != col.metadata else (),
    )


def _create_implicit(
    gallery_dir: Path,
    target: SeriesTarget,
    *,
    dry_run: bool,
    new_id: Callable[[], str],
) -> ImplicitChanges:
    """Create a new implicit collection."""
    target_dir = _collection_target_dir(gallery_dir, target.collection_name)
    if target_dir.exists():
        return ImplicitChanges(
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
    return ImplicitChanges(created=(target.collection_name,))


def _apply_match(
    gallery_dir: Path,
    group_match: GroupMatch,
    *,
    dry_run: bool,
    new_id: Callable[[], str],
) -> ImplicitChanges:
    match group_match.existing:
        case ExistingCollection() as col:
            return _update_existing(
                gallery_dir, col, group_match.target, dry_run=dry_run
            )
        case None:
            return _create_implicit(
                gallery_dir, group_match.target, dry_run=dry_run, new_id=new_id
            )


def _delete_orphaned_implicit(
    index: ImplicitIndex,
    matches: list[GroupMatch],
    *,
    dry_run: bool,
) -> ImplicitChanges:
    """Delete implicit collections no longer backed by any album series."""
    kept = {m.existing.metadata.id for m in matches if m.existing is not None}
    orphans = [col for col in index.implicit if col.metadata.id not in kept]
    if not dry_run:
        for col in orphans:
            shutil.rmtree(col.path)
    return ImplicitChanges(deleted=tuple(col.name for col in orphans))


def refresh_implicit_collections(
    gallery_dir: Path,
    albums: tuple[AlbumInfo, ...],
    existing: tuple[ExistingCollection, ...],
    *,
    dry_run: bool,
    new_id: Callable[[], str],
) -> ImplicitChanges:
    """Create, update, rename, and delete implicit collections from album series.

    Nothing is written when any group fails to match: name conflicts are
    detected on the whole plan first.
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
    return ImplicitChanges.merge(
        [
            *(
                _apply_match(gallery_dir, m, dry_run=dry_run, new_id=new_id)
                for m in matches
            ),
            _delete_orphaned_implicit(index, matches, dry_run=dry_run),
        ]
    )
