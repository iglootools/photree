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
from ..fsprotocol import ALBUMS_DIR, COLLECTIONS_DIR


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


def _try_scan_album(
    album_dir: Path,
) -> _AlbumInfo | CollectionRefreshError:
    """Validate and scan a single album. Returns info or error."""
    if check_album_naming(album_dir.name):
        return CollectionRefreshError(f"album '{album_dir.name}': unparseable name")

    parsed = parse_album_name(album_dir.name)
    if parsed is None:
        return CollectionRefreshError(f"album '{album_dir.name}': unparseable name")

    meta = load_album_metadata(album_dir)
    if meta is None:
        return CollectionRefreshError(
            f"album '{album_dir.name}': missing album metadata"
        )

    return _AlbumInfo(path=album_dir, album_id=meta.id, parsed=parsed)


def _scan_albums(
    gallery_dir: Path,
) -> tuple[list[_AlbumInfo], list[CollectionRefreshError]]:
    """Scan and validate all albums. Returns (valid_albums, errors)."""
    results = [_try_scan_album(d) for d in discover_albums(gallery_dir / ALBUMS_DIR)]
    return (
        [r for r in results if isinstance(r, _AlbumInfo)],
        [r for r in results if isinstance(r, CollectionRefreshError)],
    )


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
    return [
        _ExistingCollection(path=col_dir, metadata=meta, name=col_dir.name)
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
        for meta in [load_collection_metadata(col_dir)]
        if meta is not None
    ]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _compute_date_string(dates: list[str]) -> str:
    """Compute a date string that covers all given album dates.

    Same date → that date. Different dates → min-max range.
    """
    if not dates:
        return ""
    if len(dates) == 1:
        return dates[0]

    ranges = [rng for d in dates for rng in [_album_date_range(d)] if rng is not None]
    if not ranges:
        return dates[0]

    min_start = min(s for s, _ in ranges)
    max_end = max(e for _, e in ranges)

    if min_start == max_end:
        return str(min_start)

    return f"{min_start}--{max_end}"


def _collection_target_dir(gallery_dir: Path, name: str) -> Path:
    """Compute the target directory for a collection."""
    year = parse_collection_year(name)
    if year is not None:
        return gallery_dir / COLLECTIONS_DIR / year / name
    else:
        return gallery_dir / COLLECTIONS_DIR / name


def _build_collection_name(series_title: str, album_dates: list[str]) -> str:
    """Build the canonical collection name for a series."""
    date_str = _compute_date_string(album_dates)
    raw_name = f"{date_str} - {series_title}" if date_str else series_title
    return reconstruct_collection_name(parse_collection_name(raw_name))


def _rename_collection_dir(
    gallery_dir: Path,
    col: _ExistingCollection,
    new_name: str,
) -> _ExistingCollection:
    """Rename a collection directory, returning the updated _ExistingCollection."""
    new_path = _collection_target_dir(gallery_dir, new_name)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    col.path.rename(new_path)
    return _ExistingCollection(path=new_path, metadata=col.metadata, name=new_name)


def _rename_album_dir(
    album: _AlbumInfo,
    new_parsed: ParsedAlbumName,
) -> tuple[str, str] | None:
    """Rename an album directory if the name changed. Returns (old, new) or None."""
    new_name = reconstruct_name(new_parsed)
    if new_name == album.path.name:
        return None
    new_path = album.path.parent / new_name
    album.path.rename(new_path)
    return (album.path.name, new_name)


# ---------------------------------------------------------------------------
# Implicit collection: update existing
# ---------------------------------------------------------------------------


def _update_existing_implicit(
    gallery_dir: Path,
    col: _ExistingCollection,
    collection_name: str,
    album_ids: list[str],
    *,
    dry_run: bool,
) -> tuple[_ExistingCollection, str | None, str | None]:
    """Update an existing implicit collection.

    Returns (updated_col, renamed_pair_or_None, updated_name_or_None).
    """
    renamed_pair: str | None = None
    updated_name: str | None = None

    # Rename if date range changed the name
    if col.name != collection_name:
        if not dry_run:
            col = _rename_collection_dir(gallery_dir, col, collection_name)
        renamed_pair = collection_name

    # Update members
    new_meta = CollectionMetadata(
        id=col.metadata.id,
        kind=col.metadata.kind,
        lifecycle=CollectionLifecycle.IMPLICIT,
        albums=album_ids,
        collections=col.metadata.collections,
        images=col.metadata.images,
        videos=col.metadata.videos,
    )
    if new_meta != col.metadata:
        if not dry_run:
            save_collection_metadata(col.path, new_meta)
        updated_name = collection_name

    return col, renamed_pair, updated_name


# ---------------------------------------------------------------------------
# Implicit collection: detect rename
# ---------------------------------------------------------------------------


def _find_renamed_implicit(
    existing: list[_ExistingCollection],
    active_ids: set[str],
    album_ids: list[str],
) -> _ExistingCollection | None:
    """Find an implicit collection whose members match (rename detection)."""
    album_set = set(album_ids)
    return next(
        (
            col
            for col in existing
            if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
            and col.metadata.id not in active_ids
            and set(col.metadata.albums) == album_set
        ),
        None,
    )


def _apply_rename(
    gallery_dir: Path,
    col: _ExistingCollection,
    collection_name: str,
    album_ids: list[str],
    *,
    dry_run: bool,
) -> tuple[str, str]:
    """Rename an implicit collection (preserving ID). Returns (old_name, new_name)."""
    old_name = col.name
    if not dry_run:
        new_path = _collection_target_dir(gallery_dir, collection_name)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        col.path.rename(new_path)
        new_meta = CollectionMetadata(
            id=col.metadata.id,
            kind=col.metadata.kind,
            lifecycle=CollectionLifecycle.IMPLICIT,
            albums=album_ids,
            collections=col.metadata.collections,
            images=col.metadata.images,
            videos=col.metadata.videos,
        )
        save_collection_metadata(new_path, new_meta)
    return (old_name, collection_name)


# ---------------------------------------------------------------------------
# Implicit collection: create new
# ---------------------------------------------------------------------------


def _create_implicit(
    gallery_dir: Path,
    collection_name: str,
    album_ids: list[str],
    *,
    dry_run: bool,
) -> str | CollectionRefreshError:
    """Create a new implicit collection. Returns name or error."""
    target = _collection_target_dir(gallery_dir, collection_name)
    if target.exists():
        return CollectionRefreshError(
            f"cannot create implicit collection '{collection_name}': "
            f"directory already exists"
        )

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
    return collection_name


# ---------------------------------------------------------------------------
# Implicit collection: delete orphaned
# ---------------------------------------------------------------------------


def _delete_orphaned_implicit(
    existing: list[_ExistingCollection],
    active_ids: set[str],
    *,
    dry_run: bool,
) -> list[str]:
    """Delete implicit collections no longer backed by any album series."""
    deleted: list[str] = []
    for col in existing:
        if (
            col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
            and col.metadata.id not in active_ids
        ):
            if not dry_run:
                shutil.rmtree(col.path)
            deleted.append(col.name)
    return deleted


# ---------------------------------------------------------------------------
# Implicit collection: top-level refresh
# ---------------------------------------------------------------------------


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
    errors: list[CollectionRefreshError] = []

    # Group albums by series
    series_albums: defaultdict[str, list[_AlbumInfo]] = defaultdict(list)
    for album in albums:
        if album.parsed.series is not None:
            series_albums[album.parsed.series].append(album)

    # Index existing implicit collections by title
    implicit_cols = [
        col
        for col in existing
        if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
    ]
    implicit_by_title = {
        parse_collection_name(col.name).title: col for col in implicit_cols
    }

    active_implicit_ids: set[str] = set()

    for series_title, series_album_list in series_albums.items():
        album_dates = [a.parsed.date for a in series_album_list]
        collection_name = _build_collection_name(series_title, album_dates)
        album_ids = sorted(a.album_id for a in series_album_list)

        existing_col = implicit_by_title.get(series_title)
        if existing_col is not None:
            # Update existing implicit collection
            active_implicit_ids.add(existing_col.metadata.id)
            _, renamed_pair, updated_name = _update_existing_implicit(
                gallery_dir,
                existing_col,
                collection_name,
                album_ids,
                dry_run=dry_run,
            )
            if renamed_pair is not None:
                renamed.append((existing_col.name, renamed_pair))
            if updated_name is not None:
                updated.append(updated_name)
        else:
            # Try rename detection (members match an existing implicit)
            renamed_from = _find_renamed_implicit(
                existing, active_implicit_ids, album_ids
            )
            if renamed_from is not None:
                active_implicit_ids.add(renamed_from.metadata.id)
                renamed.append(
                    _apply_rename(
                        gallery_dir,
                        renamed_from,
                        collection_name,
                        album_ids,
                        dry_run=dry_run,
                    )
                )
            else:
                # Create new
                result = _create_implicit(
                    gallery_dir, collection_name, album_ids, dry_run=dry_run
                )
                if isinstance(result, CollectionRefreshError):
                    errors.append(result)
                else:
                    created.append(result)

    deleted = _delete_orphaned_implicit(existing, active_implicit_ids, dry_run=dry_run)

    return created, updated, renamed, deleted, errors


# ---------------------------------------------------------------------------
# Smart collection logic
# ---------------------------------------------------------------------------


def _overlaps(start_a: date, end_a: date, start_b: date, end_b: date) -> bool:
    """Check if two date ranges overlap."""
    return start_a <= end_b and end_a >= start_b


def _refresh_smart_collections(
    albums: list[_AlbumInfo],
    all_collections: list[_ExistingCollection],
    *,
    dry_run: bool,
) -> list[str]:
    """Materialize members for smart collections by date range.

    Returns list of updated collection names.
    """
    updated: list[str] = []

    col_date_ranges: dict[str, tuple[date, date]] = {
        col.metadata.id: rng
        for col in all_collections
        for parsed_col in [parse_collection_name(col.name)]
        if parsed_col.date is not None
        for rng in [_album_date_range(parsed_col.date)]
        if rng is not None
    }

    album_ranges = [
        (album.album_id, rng)
        for album in albums
        for rng in [_album_date_range(album.parsed.date)]
        if rng is not None
    ]

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

        matching_album_ids = sorted(
            aid
            for aid, (a_start, a_end) in album_ranges
            if _overlaps(a_start, a_end, col_start, col_end)
        )

        matching_col_ids = sorted(
            cid
            for cid, (o_start, o_end) in col_date_ranges.items()
            if cid != col.metadata.id and _overlaps(o_start, o_end, col_start, col_end)
        )

        new_meta = CollectionMetadata(
            id=col.metadata.id,
            kind=col.metadata.kind,
            lifecycle=col.metadata.lifecycle,
            albums=matching_album_ids,
            collections=matching_col_ids,
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


def _strip_series(album: _AlbumInfo) -> ParsedAlbumName:
    """Return parsed name with series removed."""
    return ParsedAlbumName(
        date=album.parsed.date,
        part=album.parsed.part,
        private=album.parsed.private,
        series=None,
        title=album.parsed.title,
        location=album.parsed.location,
    )


def _add_series(album: _AlbumInfo, series: str) -> ParsedAlbumName:
    """Return parsed name with series added."""
    return ParsedAlbumName(
        date=album.parsed.date,
        part=album.parsed.part,
        private=album.parsed.private,
        series=series,
        title=album.parsed.title,
        location=album.parsed.location,
    )


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
    explicit_by_title = {
        parse_collection_name(col.name).title: col
        for col in existing
        if col.metadata.lifecycle == CollectionLifecycle.EXPLICIT
    }

    implicit_by_album = {
        album_id: col
        for col in existing
        if col.metadata.lifecycle == CollectionLifecycle.IMPLICIT
        for album_id in col.metadata.albums
    }

    renames: list[tuple[str, str]] = []

    for album in albums:
        if album.parsed.series is not None and album.parsed.series in explicit_by_title:
            # Explicit collection owns this series → strip from album name
            new_parsed = _strip_series(album)
        elif album.parsed.series is None and album.album_id in implicit_by_album:
            # Implicit collection contains this album → add series
            col = implicit_by_album[album.album_id]
            col_parsed = parse_collection_name(col.name)
            new_parsed = _add_series(album, col_parsed.title)
        else:
            new_parsed = None

        if new_parsed is not None and not dry_run:
            result = _rename_album_dir(album, new_parsed)
            if result is not None:
                renames.append(result)
        elif new_parsed is not None:
            # dry_run: still report the rename
            new_name = reconstruct_name(new_parsed)
            if new_name != album.path.name:
                renames.append((album.path.name, new_name))

    return renames, []


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
    albums, scan_errors = _scan_albums(gallery_dir)
    if scan_errors:
        return CollectionRefreshResult(errors=tuple(scan_errors))

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
    smart_updated = _refresh_smart_collections(albums, existing, dry_run=dry_run)

    return CollectionRefreshResult(
        created=tuple(created),
        updated=tuple([*updated, *smart_updated]),
        renamed=tuple(renamed),
        deleted=tuple(deleted),
        album_renames=tuple(album_renames),
    )
