"""Render a browsable directory structure with symlinks.

Creates ``<gallery-dir>/browsable/`` with a hierarchy of symlinks
organized by visibility (public/private), type (albums/collections),
and grouping (by-year, all-time, by-chapter).

Called by ``gallery refresh`` after album and collection refresh.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..album.naming import parse_album_name
from ..album.store.album_discovery import discover_albums
from ..album.store.media_metadata import load_media_metadata
from ..album.store.media_sources_discovery import discover_media_sources
from ..album.store.metadata import load_album_metadata
from ..album.store.protocol import MediaSource
from ..collection.naming import parse_collection_name, parse_collection_year
from ..collection.store.collection_discovery import discover_collections
from ..collection.store.metadata import load_collection_metadata
from ..collection.store.protocol import CollectionStrategy
from ..fsprotocol import ALBUMS_DIR, BROWSABLE_DIR, COLLECTIONS_DIR


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrowsableRefreshError:
    """An error encountered during browsable refresh."""

    message: str


@dataclass(frozen=True)
class BrowsableRefreshResult:
    """Result of a browsable refresh run."""

    albums_rendered: int = 0
    collections_rendered: int = 0
    symlinks_created: int = 0
    errors: tuple[BrowsableRefreshError, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Safety check
# ---------------------------------------------------------------------------


def _validate_browsable_dir(browsable_dir: Path) -> str | None:
    """Validate that browsable/ only contains directories and symlinks.

    Returns an error message if regular files are found, else None.
    """
    if not browsable_dir.exists():
        return None

    regular_files = [
        path
        for path in browsable_dir.rglob("*")
        if path.is_file() and not path.is_symlink()
    ]
    if regular_files:
        return (
            f"browsable/ contains regular file: {regular_files[0]}. "
            f"Expected only directories and symlinks. "
            f"Remove the file manually or delete browsable/ to proceed."
        )
    else:
        return None


# ---------------------------------------------------------------------------
# Gallery scanning — data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AlbumEntry:
    """Album info needed for rendering."""

    path: Path
    album_id: str
    name: str
    private: bool
    year: str
    jpg_dirs: list[str]
    vid_dirs: list[str]


@dataclass(frozen=True)
class _CollectionEntry:
    """Collection info needed for rendering."""

    path: Path
    collection_id: str
    name: str
    private: bool
    year: str | None
    strategy: CollectionStrategy
    album_ids: list[str]
    collection_ids: list[str]
    image_ids: list[str]
    video_ids: list[str]


@dataclass(frozen=True)
class _MediaLocation:
    """Where a media item's browsable file lives."""

    album_path: Path
    jpg_dir: str
    vid_dir: str
    key: str


# ---------------------------------------------------------------------------
# Gallery scanning — album scanning
# ---------------------------------------------------------------------------


def _try_scan_album(
    album_dir: Path,
) -> _AlbumEntry | BrowsableRefreshError | None:
    """Scan a single album. Returns entry, error, or None (skip)."""
    meta = load_album_metadata(album_dir)
    if meta is None:
        return None

    parsed = parse_album_name(album_dir.name)
    if parsed is None:
        return None

    # Extract year from the date prefix (all formats start with YYYY)
    year = parsed.date[:4]

    media_sources = discover_media_sources(album_dir)
    return _AlbumEntry(
        path=album_dir,
        album_id=meta.id,
        name=album_dir.name,
        private=parsed.private,
        year=year,
        jpg_dirs=[ms.jpg_dir for ms in media_sources],
        vid_dirs=[ms.vid_dir for ms in media_sources],
    )


def _build_media_locations(
    album_dir: Path,
    media_sources: list[MediaSource],
) -> dict[str, _MediaLocation]:
    """Build media ID → browsable file location mappings for one album."""
    media_meta = load_media_metadata(album_dir)
    if media_meta is None or not media_sources:
        return {}

    ms = media_sources[0]  # primary media source
    return {
        mid: _MediaLocation(
            album_path=album_dir, jpg_dir=ms.jpg_dir, vid_dir=ms.vid_dir, key=key
        )
        for source in media_meta.media_sources.values()
        for mid, key in [*source.images.items(), *source.videos.items()]
    }


def _scan_album_entries(
    gallery_dir: Path,
) -> tuple[
    dict[str, _AlbumEntry], dict[str, _MediaLocation], list[BrowsableRefreshError]
]:
    """Scan albums and build album + media location lookups."""
    results = [_try_scan_album(d) for d in discover_albums(gallery_dir / ALBUMS_DIR)]

    albums = {r.album_id: r for r in results if isinstance(r, _AlbumEntry)}
    errors = [r for r in results if isinstance(r, BrowsableRefreshError)]

    media_locations: dict[str, _MediaLocation] = {}
    for album in albums.values():
        media_locations.update(
            _build_media_locations(album.path, discover_media_sources(album.path))
        )

    return albums, media_locations, errors


# ---------------------------------------------------------------------------
# Gallery scanning — collection scanning
# ---------------------------------------------------------------------------


def _scan_collection_entries(
    gallery_dir: Path,
) -> dict[str, _CollectionEntry]:
    """Scan collections and build collection lookup."""
    return {
        meta.id: _CollectionEntry(
            path=col_dir,
            collection_id=meta.id,
            name=col_dir.name,
            private=parse_collection_name(col_dir.name).private,
            year=parse_collection_year(col_dir.name),
            strategy=meta.strategy,
            album_ids=meta.albums,
            collection_ids=meta.collections,
            image_ids=meta.images,
            video_ids=meta.videos,
        )
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
        for meta in [load_collection_metadata(col_dir)]
        if meta is not None
    }


# ---------------------------------------------------------------------------
# Symlink helpers
# ---------------------------------------------------------------------------


def _make_relative_symlink(target: Path, link: Path) -> None:
    """Create a relative symlink from *link* pointing to *target*."""
    link.parent.mkdir(parents=True, exist_ok=True)
    rel_target = os.path.relpath(target, link.parent)
    os.symlink(rel_target, link)


def _matches_key(filename: str, key: str) -> bool:
    """Check if a filename matches a media key."""
    if filename.upper().startswith("IMG_"):
        return "".join(c for c in filename if c.isdigit()) == key
    else:
        return Path(filename).stem == key


def _symlink_dir_if_exists(src: Path, link: Path) -> int:
    """Create a symlink to src if it exists. Returns 1 on success, 0 otherwise."""
    if src.is_dir():
        _make_relative_symlink(src, link)
        return 1
    else:
        return 0


# ---------------------------------------------------------------------------
# Album rendering
# ---------------------------------------------------------------------------


def _render_album(album: _AlbumEntry, target_dir: Path) -> int:
    """Render an album: symlinks to jpg + vid dirs. Returns symlink count."""
    album_target = target_dir / album.name
    return sum(
        _symlink_dir_if_exists(album.path / d, album_target / d)
        for d in [*album.jpg_dirs, *album.vid_dirs]
    )


# ---------------------------------------------------------------------------
# Collection rendering — media helpers
# ---------------------------------------------------------------------------


def _render_media_files(
    media_ids: list[str],
    media_locations: dict[str, _MediaLocation],
    target_subdir: Path,
    dir_attr: str,
) -> int:
    """Symlink individual media files into target_subdir. Returns count."""
    count = 0
    for mid in media_ids:
        loc = media_locations.get(mid)
        if loc is not None:
            browsable_dir = loc.album_path / getattr(loc, dir_attr)
            if browsable_dir.is_dir():
                for f in browsable_dir.iterdir():
                    if f.is_file() and _matches_key(f.name, loc.key):
                        _make_relative_symlink(f, target_subdir / f.name)
                        count += 1
    return count


# ---------------------------------------------------------------------------
# Collection rendering (recursive)
# ---------------------------------------------------------------------------


def _render_collection(
    collection: _CollectionEntry,
    target_dir: Path,
    albums: dict[str, _AlbumEntry],
    collections: dict[str, _CollectionEntry],
    media_locations: dict[str, _MediaLocation],
    visited: set[str],
) -> tuple[int, list[BrowsableRefreshError]]:
    """Render a collection recursively. Returns (symlink_count, errors)."""
    if collection.collection_id in visited:
        return 0, [
            BrowsableRefreshError(
                f"cycle detected: collection '{collection.name}' "
                f"(id: {collection.collection_id}) already visited"
            )
        ]
    visited = {*visited, collection.collection_id}
    col_target = target_dir / collection.name

    album_count = _render_collection_albums(collection, col_target, albums)
    sub_count, sub_errors = _render_collection_subcollections(
        collection, col_target, albums, collections, media_locations, visited
    )
    image_count = _render_media_files(
        collection.image_ids, media_locations, col_target / "images", "jpg_dir"
    )
    video_count = _render_media_files(
        collection.video_ids, media_locations, col_target / "videos", "vid_dir"
    )

    return album_count + sub_count + image_count + video_count, sub_errors


def _render_collection_albums(
    collection: _CollectionEntry,
    col_target: Path,
    albums: dict[str, _AlbumEntry],
) -> int:
    """Render album members of a collection."""
    return sum(
        _render_album(album, col_target / "albums")
        for album_id in collection.album_ids
        for album in [albums.get(album_id)]
        if album is not None
    )


def _render_collection_subcollections(
    collection: _CollectionEntry,
    col_target: Path,
    albums: dict[str, _AlbumEntry],
    collections: dict[str, _CollectionEntry],
    media_locations: dict[str, _MediaLocation],
    visited: set[str],
) -> tuple[int, list[BrowsableRefreshError]]:
    """Render sub-collection members recursively.

    Uses imperative accumulation because each recursive call may
    produce errors that must be collected.
    """
    count = 0
    errors: list[BrowsableRefreshError] = []
    for col_id in collection.collection_ids:
        sub = collections.get(col_id)
        if sub is not None:
            sub_count, sub_errors = _render_collection(
                sub,
                col_target / "collections",
                albums,
                collections,
                media_locations,
                visited,
            )
            count += sub_count
            errors.extend(sub_errors)
    return count, errors


# ---------------------------------------------------------------------------
# Top-level rendering
# ---------------------------------------------------------------------------


def _collection_bucket(col: _CollectionEntry) -> tuple[str, str]:
    """Determine the bucket path for a collection."""
    match col.strategy:
        case CollectionStrategy.CHAPTER:
            return ("by-chapter", "")
        case _:
            if col.year is not None:
                return ("by-year", col.year)
            else:
                return ("all-time", "")


def _album_target_dir(browsable_dir: Path, album: _AlbumEntry) -> Path:
    """Compute the target directory for an album in the browsable tree."""
    visibility = "private" if album.private else "public"
    return browsable_dir / visibility / "albums" / "by-year" / album.year


def _collection_target_dir(browsable_dir: Path, col: _CollectionEntry) -> Path:
    """Compute the target directory for a collection in the browsable tree."""
    visibility = "private" if col.private else "public"
    bucket, sub_path = _collection_bucket(col)
    parts = [visibility, "collections", bucket, *([sub_path] if sub_path else [])]
    return browsable_dir / Path(*parts)


def _render_all_albums(
    albums: dict[str, _AlbumEntry],
    browsable_dir: Path,
) -> tuple[int, int]:
    """Render all albums into browsable/. Returns (album_count, symlink_count)."""
    total_symlinks = sum(
        _render_album(album, _album_target_dir(browsable_dir, album))
        for album in albums.values()
    )
    return len(albums), total_symlinks


def _render_all_collections(
    collections: dict[str, _CollectionEntry],
    albums: dict[str, _AlbumEntry],
    media_locations: dict[str, _MediaLocation],
    browsable_dir: Path,
) -> tuple[int, int, list[BrowsableRefreshError]]:
    """Render all collections into browsable/. Returns (count, symlinks, errors).

    Uses imperative accumulation because each collection render may
    produce errors that must be collected.
    """
    total_symlinks = 0
    errors: list[BrowsableRefreshError] = []

    for col in collections.values():
        target = _collection_target_dir(browsable_dir, col)
        count, col_errors = _render_collection(
            col, target, albums, collections, media_locations, set()
        )
        total_symlinks += count
        errors.extend(col_errors)

    return len(collections), total_symlinks, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def refresh_browsable(
    gallery_dir: Path,
    *,
    dry_run: bool = False,
) -> BrowsableRefreshResult:
    """Render the browsable directory structure.

    1. Scan gallery for albums and collections
    2. Validate and clean existing browsable/ directory
    3. Render albums by year under public/private
    4. Render collections by year/chapter/all-time under public/private
    """
    browsable_dir = gallery_dir / BROWSABLE_DIR

    safety_error = _validate_browsable_dir(browsable_dir)
    if safety_error is not None:
        return BrowsableRefreshResult(errors=(BrowsableRefreshError(safety_error),))

    albums, media_locations, scan_errors = _scan_album_entries(gallery_dir)
    if scan_errors:
        return BrowsableRefreshResult(errors=tuple(scan_errors))

    collections = _scan_collection_entries(gallery_dir)

    if dry_run:
        return BrowsableRefreshResult(
            albums_rendered=len(albums),
            collections_rendered=len(collections),
        )

    if browsable_dir.exists():
        shutil.rmtree(browsable_dir)

    album_count, album_symlinks = _render_all_albums(albums, browsable_dir)
    col_count, col_symlinks, col_errors = _render_all_collections(
        collections, albums, media_locations, browsable_dir
    )

    return BrowsableRefreshResult(
        albums_rendered=album_count,
        collections_rendered=col_count,
        symlinks_created=album_symlinks + col_symlinks,
        errors=tuple(col_errors),
    )
