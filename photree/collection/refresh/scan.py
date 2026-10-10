"""Scan the gallery's albums and collections for a collection refresh.

Phase 1 of the refresh: every album name is light-checked and every
metadata file read up front, so a refresh that will fail reports every
problem at once and modifies nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...album.naming import (
    ParsedAlbumName,
    check_album_naming,
    check_batch_date_collisions,
    parse_album_name,
)
from ...album.store.album_discovery import discover_albums
from ...album.store.metadata import load_album_metadata
from ...album.store.protocol import AlbumMetadata
from ...foundation.layout import ALBUMS_DIR, COLLECTIONS_DIR
from ...foundation.metadata_io import read_or_none
from ..store.collection_discovery import discover_collections
from ..store.metadata import (
    load_collection_metadata,
)
from ..store.protocol import (
    CollectionMetadata,
)
from .result import (
    CollectionRefreshError,
    CollectionRefreshErrorKind,
)


@dataclass(frozen=True)
class AlbumInfo:
    """Parsed album info needed for collection refresh."""

    path: Path
    album_id: str
    parsed: ParsedAlbumName


@dataclass(frozen=True)
class ExistingCollection:
    """An existing collection on disk."""

    path: Path
    metadata: CollectionMetadata
    name: str


@dataclass(frozen=True)
class GalleryScan:
    albums: tuple[AlbumInfo, ...]
    collections: tuple[ExistingCollection, ...]
    errors: tuple[CollectionRefreshError, ...]


def _try_scan_album(album_dir: Path) -> AlbumInfo | CollectionRefreshError:
    """Validate and scan a single album. Returns info or error."""
    issues = check_album_naming(album_dir.name)
    parsed = parse_album_name(album_dir.name)
    meta = read_or_none(load_album_metadata, album_dir)
    match (issues, parsed, meta):
        case ((), ParsedAlbumName() as valid, AlbumMetadata() as valid_meta):
            return AlbumInfo(path=album_dir, album_id=valid_meta.id, parsed=valid)
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


def _try_scan_collection(col_dir: Path) -> ExistingCollection | CollectionRefreshError:
    meta = read_or_none(load_collection_metadata, col_dir)
    return (
        ExistingCollection(path=col_dir, metadata=meta, name=col_dir.name)
        if meta is not None
        else CollectionRefreshError(
            CollectionRefreshErrorKind.COLLECTION_UNREADABLE_METADATA, path=col_dir
        )
    )


def scan_existing_collections(
    gallery_dir: Path,
) -> tuple[tuple[ExistingCollection, ...], tuple[CollectionRefreshError, ...]]:
    """Find all existing collections in the gallery."""
    results = [
        _try_scan_collection(d)
        for d in discover_collections(gallery_dir / COLLECTIONS_DIR)
    ]
    return (
        tuple(r for r in results if isinstance(r, ExistingCollection)),
        tuple(r for r in results if isinstance(r, CollectionRefreshError)),
    )


def _date_collision_errors(
    albums: tuple[AlbumInfo, ...],
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


def scan_gallery(gallery_dir: Path) -> GalleryScan:
    """Scan albums and collections; collect every reason to stop.

    Collisions are only checked once every name parses, since an
    unparseable name has no date to collide on.
    """
    album_results = [
        _try_scan_album(d) for d in discover_albums(gallery_dir / ALBUMS_DIR)
    ]
    albums = tuple(r for r in album_results if isinstance(r, AlbumInfo))
    album_errors = tuple(
        r for r in album_results if isinstance(r, CollectionRefreshError)
    )
    collections, collection_errors = scan_existing_collections(gallery_dir)
    return GalleryScan(
        albums=albums,
        collections=collections,
        errors=(
            *album_errors,
            *collection_errors,
            *(() if album_errors else _date_collision_errors(albums)),
        ),
    )
