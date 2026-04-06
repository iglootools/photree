"""Refresh implicit collections and smart collection members.

Called by ``gallery refresh`` to:
1. Detect album series → create/update/rename/delete implicit collections
2. Materialize smart collection members by date range
3. Sync album titles with collection lifecycle changes
"""

from __future__ import annotations

import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..album.naming import (
    ParsedAlbumName,
    _album_date_range,
    check_album_naming,
    parse_album_name,
    reconstruct_name,
)
from ..album.store.album_discovery import discover_albums
from ..album.store.metadata import load_album_metadata
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
    CollectionKind,
    CollectionLifecycle,
    CollectionMetadata,
)

COLLECTIONS_DIR = "collections"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectionRefreshError:
    """An error encountered during collection refresh."""

    message: str


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
# Album scanning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AlbumInfo:
    """Parsed album info needed for collection refresh."""

    path: Path
    album_id: str
    parsed: ParsedAlbumName


def _scan_albums(
    gallery_dir: Path,
) -> tuple[list[_AlbumInfo], list[CollectionRefreshError]]:
    """Scan and validate all albums. Returns (valid_albums, errors)."""
    albums: list[_AlbumInfo] = []
    errors: list[CollectionRefreshError] = []

    for album_dir in discover_albums(gallery_dir):
        # Light check: naming only (no EXIF)
        naming_issues = check_album_naming(album_dir.name)
        if naming_issues:
            errors.append(
                CollectionRefreshError(f"album '{album_dir.name}': unparseable name")
            )
            continue

        parsed = parse_album_name(album_dir.name)
        if parsed is None:
            errors.append(
                CollectionRefreshError(f"album '{album_dir.name}': unparseable name")
            )
            continue

        meta = load_album_metadata(album_dir)
        if meta is None:
            errors.append(
                CollectionRefreshError(
                    f"album '{album_dir.name}': missing album metadata"
                )
            )
            continue

        albums.append(_AlbumInfo(path=album_dir, album_id=meta.id, parsed=parsed))

    return albums, errors


# ---------------------------------------------------------------------------
# Existing collection scanning
# ---------------------------------------------------------------------------


@dataclass
class _ExistingCollection:
    """An existing collection on disk."""

    path: Path
    metadata: CollectionMetadata
    name: str


def _scan_existing_collections(gallery_dir: Path) -> list[_ExistingCollection]:
    """Find all existing collections in the gallery."""
    result = []
    for col_dir in discover_collections(gallery_dir):
        meta = load_collection_metadata(col_dir)
        if meta is not None:
            result.append(
                _ExistingCollection(path=col_dir, metadata=meta, name=col_dir.name)
            )
    return result


# ---------------------------------------------------------------------------
# Implicit collection logic
# ---------------------------------------------------------------------------


def _compute_date_string(dates: list[str]) -> str:
    """Compute a date string that covers all given album dates.

    Same date → that date. Different dates → min-max range.
    """
    if not dates:
        return ""
    if len(dates) == 1:
        return dates[0]

    # Find min start and max end across all dates
    all_starts: list[date] = []
    all_ends: list[date] = []
    for d in dates:
        rng = _album_date_range(d)
        if rng is not None:
            all_starts.append(rng[0])
            all_ends.append(rng[1])

    if not all_starts:
        return dates[0]

    min_start = min(all_starts)
    max_end = max(all_ends)

    if min_start == max_end:
        return str(min_start)

    return f"{min_start}--{max_end}"


def _collection_target_dir(gallery_dir: Path, name: str) -> Path:
    """Compute the target directory for a collection."""
    year = parse_collection_year(name)
    if year is not None:
        return gallery_dir / COLLECTIONS_DIR / year / name
    return gallery_dir / COLLECTIONS_DIR / name


def _refresh_implicit_collections(
    gallery_dir: Path,
    albums: list[_AlbumInfo],
    existing: list[_ExistingCollection],
    *,
    dry_run: bool,
) -> tuple[
    list[str], list[str], list[tuple[str, str]], list[str], list[CollectionRefreshError]
]:
    """Refresh implicit collections from album series.

    Returns (created, updated, renamed, deleted, errors).
    """
    created: list[str] = []
    updated: list[str] = []
    renamed: list[tuple[str, str]] = []
    deleted: list[str] = []
    errors: list[CollectionRefreshError] = []

    # Group albums by series
    series_albums: defaultdict[str, list[_AlbumInfo]] = defaultdict(list)
    for album in albums:
        if album.parsed.series is not None:
            series_albums[album.parsed.series].append(album)

    # Index existing implicit collections by title
    implicit_by_title: dict[str, _ExistingCollection] = {}
    implicit_by_id: dict[str, _ExistingCollection] = {}
    for col in existing:
        if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT:
            parsed_col = parse_collection_name(col.name)
            implicit_by_title[parsed_col.title] = col
            implicit_by_id[col.metadata.id] = col

    # Track which implicit collections are still active
    active_implicit_ids: set[str] = set()

    for series_title, series_album_list in series_albums.items():
        # Compute date range
        album_dates = [a.parsed.date for a in series_album_list]
        date_str = _compute_date_string(album_dates)
        collection_name = reconstruct_collection_name(
            parse_collection_name(
                f"{date_str} - {series_title}" if date_str else series_title
            )
        )

        album_ids = sorted(a.album_id for a in series_album_list)

        existing_col = implicit_by_title.get(series_title)
        if existing_col is not None:
            active_implicit_ids.add(existing_col.metadata.id)

            # Check if name changed (date range update)
            if existing_col.name != collection_name:
                if not dry_run:
                    new_path = _collection_target_dir(gallery_dir, collection_name)
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    existing_col.path.rename(new_path)
                    existing_col = _ExistingCollection(
                        path=new_path,
                        metadata=existing_col.metadata,
                        name=collection_name,
                    )
                renamed.append((existing_col.name, collection_name))

            # Update members
            new_meta = CollectionMetadata(
                id=existing_col.metadata.id,
                kind=existing_col.metadata.kind,
                lifecycle=CollectionLifecycle.IMPLICIT,
                albums=album_ids,
                collections=existing_col.metadata.collections,
                images=existing_col.metadata.images,
                videos=existing_col.metadata.videos,
            )
            if new_meta != existing_col.metadata:
                if not dry_run:
                    save_collection_metadata(existing_col.path, new_meta)
                updated.append(collection_name)
        else:
            # Check if an implicit collection exists that had all its albums
            # rename to this new series (rename detection)
            # Look for an implicit collection whose current members match
            # the albums that now have this series
            renamed_from = None
            for col in existing:
                if (
                    col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
                    and col.metadata.id not in active_implicit_ids
                    and set(col.metadata.albums) == set(album_ids)
                ):
                    renamed_from = col
                    break

            if renamed_from is not None:
                active_implicit_ids.add(renamed_from.metadata.id)
                old_name = renamed_from.name
                if not dry_run:
                    new_path = _collection_target_dir(gallery_dir, collection_name)
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    renamed_from.path.rename(new_path)
                    new_meta = CollectionMetadata(
                        id=renamed_from.metadata.id,
                        kind=renamed_from.metadata.kind,
                        lifecycle=CollectionLifecycle.IMPLICIT,
                        albums=album_ids,
                        collections=renamed_from.metadata.collections,
                        images=renamed_from.metadata.images,
                        videos=renamed_from.metadata.videos,
                    )
                    save_collection_metadata(new_path, new_meta)
                renamed.append((old_name, collection_name))
            else:
                # Create new implicit collection
                target = _collection_target_dir(gallery_dir, collection_name)
                if target.exists():
                    errors.append(
                        CollectionRefreshError(
                            f"cannot create implicit collection '{collection_name}': "
                            f"directory already exists"
                        )
                    )
                    continue

                if not dry_run:
                    target.mkdir(parents=True, exist_ok=True)
                    save_collection_metadata(
                        target,
                        CollectionMetadata(
                            id=generate_collection_id(),
                            kind=CollectionKind.MANUAL,
                            lifecycle=CollectionLifecycle.IMPLICIT,
                            albums=album_ids,
                        ),
                    )
                created.append(collection_name)

    # Delete orphaned implicit collections
    for col in existing:
        if (
            col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
            and col.metadata.id not in active_implicit_ids
        ):
            if not dry_run:
                shutil.rmtree(col.path)
            deleted.append(col.name)

    return created, updated, renamed, deleted, errors


# ---------------------------------------------------------------------------
# Smart collection logic
# ---------------------------------------------------------------------------


def _refresh_smart_collections(
    gallery_dir: Path,
    albums: list[_AlbumInfo],
    all_collections: list[_ExistingCollection],
    *,
    dry_run: bool,
) -> list[str]:
    """Materialize members for smart collections by date range.

    Returns list of updated collection names.
    """
    updated: list[str] = []

    # Build collection index for sub-collection matching
    col_date_ranges: dict[str, tuple[date, date]] = {}
    for col in all_collections:
        parsed = parse_collection_name(col.name)
        if parsed.date is not None:
            rng = _album_date_range(parsed.date)
            if rng is not None:
                col_date_ranges[col.metadata.id] = rng

    for col in all_collections:
        if col.metadata.kind != CollectionKind.SMART:
            continue

        parsed = parse_collection_name(col.name)
        if parsed.date is None:
            continue

        col_range = _album_date_range(parsed.date)
        if col_range is None:
            continue

        col_start, col_end = col_range

        # Find albums in range
        matching_album_ids: list[str] = []
        for album in albums:
            album_range = _album_date_range(album.parsed.date)
            if album_range is None:
                continue
            a_start, a_end = album_range
            # Album is in range if it overlaps with the collection range
            if a_start <= col_end and a_end >= col_start:
                matching_album_ids.append(album.album_id)

        # Find sub-collections in range
        matching_col_ids: list[str] = []
        for other_col in all_collections:
            if other_col.metadata.id == col.metadata.id:
                continue
            if other_col.metadata.id not in col_date_ranges:
                continue
            o_start, o_end = col_date_ranges[other_col.metadata.id]
            if o_start <= col_end and o_end >= col_start:
                matching_col_ids.append(other_col.metadata.id)

        new_meta = CollectionMetadata(
            id=col.metadata.id,
            kind=col.metadata.kind,
            lifecycle=col.metadata.lifecycle,
            albums=sorted(matching_album_ids),
            collections=sorted(matching_col_ids),
            images=col.metadata.images,
            videos=col.metadata.videos,
        )

        if new_meta != col.metadata:
            if not dry_run:
                save_collection_metadata(col.path, new_meta)
            updated.append(col.name)

    return updated


# ---------------------------------------------------------------------------
# Album title sync
# ---------------------------------------------------------------------------


def _sync_album_titles(
    albums: list[_AlbumInfo],
    existing: list[_ExistingCollection],
    *,
    dry_run: bool,
) -> tuple[list[tuple[str, str]], list[CollectionRefreshError]]:
    """Sync album titles with collection lifecycle changes.

    - Explicit collection with matching series title → remove series from albums
    - Implicit collection containing albums without series → add series

    Returns (album_renames, errors).
    """
    renames: list[tuple[str, str]] = []
    errors: list[CollectionRefreshError] = []

    # Index explicit collections by title
    explicit_by_title: dict[str, _ExistingCollection] = {}
    for col in existing:
        if col.metadata.lifecycle == CollectionLifecycle.EXPLICIT:
            parsed = parse_collection_name(col.name)
            explicit_by_title[parsed.title] = col

    # Index implicit collections by album ID
    implicit_by_album: dict[str, _ExistingCollection] = {}
    for col in existing:
        if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT:
            for album_id in col.metadata.albums:
                implicit_by_album[album_id] = col

    for album in albums:
        # Case 1: Album has series, explicit collection exists with that title
        # → remove series from album name
        if album.parsed.series is not None and album.parsed.series in explicit_by_title:
            new_parsed = ParsedAlbumName(
                date=album.parsed.date,
                part=album.parsed.part,
                private=album.parsed.private,
                series=None,
                title=album.parsed.title,
                location=album.parsed.location,
            )
            new_name = reconstruct_name(new_parsed)
            if new_name != album.path.name:
                if not dry_run:
                    new_path = album.path.parent / new_name
                    album.path.rename(new_path)
                renames.append((album.path.name, new_name))

        # Case 2: Album has no series, implicit collection contains it
        # → add collection title as series
        elif album.parsed.series is None and album.album_id in implicit_by_album:
            col = implicit_by_album[album.album_id]
            col_parsed = parse_collection_name(col.name)
            new_parsed = ParsedAlbumName(
                date=album.parsed.date,
                part=album.parsed.part,
                private=album.parsed.private,
                series=col_parsed.title,
                title=album.parsed.title,
                location=album.parsed.location,
            )
            new_name = reconstruct_name(new_parsed)
            if new_name != album.path.name:
                if not dry_run:
                    new_path = album.path.parent / new_name
                    album.path.rename(new_path)
                renames.append((album.path.name, new_name))

    return renames, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def refresh_collections(
    gallery_dir: Path,
    *,
    dry_run: bool = False,
) -> CollectionRefreshResult:
    """Refresh all collections in the gallery.

    1. Validate album names (light check, no EXIF)
    2. Sync album titles with existing collection lifecycle changes
    3. Re-scan albums (titles may have changed)
    4. Refresh implicit collections from album series
    5. Materialize smart collection members
    """
    # Scan albums
    albums, scan_errors = _scan_albums(gallery_dir)
    if scan_errors:
        return CollectionRefreshResult(errors=tuple(scan_errors))

    # Scan existing collections
    existing = _scan_existing_collections(gallery_dir)

    # Sync album titles first (before implicit refresh modifies collections)
    album_renames, sync_errors = _sync_album_titles(albums, existing, dry_run=dry_run)
    if sync_errors:
        return CollectionRefreshResult(
            album_renames=tuple(album_renames),
            errors=tuple(sync_errors),
        )

    # Re-scan albums after title sync (names may have changed)
    if album_renames:
        albums, scan_errors = _scan_albums(gallery_dir)
        if scan_errors:
            return CollectionRefreshResult(
                album_renames=tuple(album_renames),
                errors=tuple(scan_errors),
            )

    # Refresh implicit collections
    created, updated, renamed, deleted, implicit_errors = _refresh_implicit_collections(
        gallery_dir, albums, existing, dry_run=dry_run
    )

    if implicit_errors:
        return CollectionRefreshResult(
            created=tuple(created),
            updated=tuple(updated),
            renamed=tuple(renamed),
            deleted=tuple(deleted),
            album_renames=tuple(album_renames),
            errors=tuple(implicit_errors),
        )

    # Re-scan collections after implicit refresh (new ones may have been created)
    existing = _scan_existing_collections(gallery_dir)

    # Materialize smart collection members
    smart_updated = _refresh_smart_collections(
        gallery_dir, albums, existing, dry_run=dry_run
    )

    return CollectionRefreshResult(
        created=tuple(created),
        updated=tuple([*updated, *smart_updated]),
        renamed=tuple(renamed),
        deleted=tuple(deleted),
        album_renames=tuple(album_renames),
    )
