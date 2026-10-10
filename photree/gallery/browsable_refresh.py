"""Render a browsable directory structure with symlinks.

Creates ``<gallery-dir>/browsable/`` with a hierarchy of symlinks
organized by visibility (public/private), type (albums/collections),
and grouping (by-year, all-time, by-chapter).

Called by ``gallery refresh`` after album and collection refresh.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..album.naming import parse_album_name
from ..album.store.album_discovery import discover_albums
from ..album.store.media_metadata import load_media_metadata
from ..album.store.media_source import MediaSource
from ..album.store.media_sources_discovery import discover_media_sources
from ..album.store.metadata import load_album_metadata
from ..collection.naming import parse_collection_name, parse_collection_year
from ..collection.store.collection_discovery import discover_collections
from ..collection.store.metadata import load_collection_metadata
from ..collection.store.protocol import CollectionMetadata, CollectionStrategy
from ..fsprotocol import ALBUMS_DIR, BROWSABLE_DIR, COLLECTIONS_DIR
from .metadata_scan import read_or_none

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class BrowsableRefreshErrorKind(StrEnum):
    """Why the browsable tree could not be (fully) rendered."""

    REGULAR_FILE = "regular-file"
    """``path``: a regular file inside ``browsable/`` (only links expected)."""

    ALBUM_MISSING_METADATA = "album-missing-metadata"
    """``path``: album whose ``album.yaml`` cannot be read."""

    ALBUM_UNPARSEABLE_NAME = "album-unparseable-name"
    """``path``: album whose name has no parseable date."""

    COLLECTION_UNREADABLE_METADATA = "collection-unreadable-metadata"
    """``path``: collection whose ``collection.yaml`` cannot be read."""

    CYCLE = "cycle"
    """``path``: collection reached again through its own members."""


@dataclass(frozen=True)
class BrowsableRefreshError:
    """An error encountered during browsable refresh."""

    kind: BrowsableRefreshErrorKind
    path: Path
    collection_id: str | None = None


class DanglingMemberKind(StrEnum):
    """Which member list of a collection references an unknown ID."""

    ALBUM = "album"
    COLLECTION = "collection"
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True)
class DanglingMember:
    """A collection member ID that resolves to nothing in the gallery.

    Rendering skips it, so it is reported rather than failing the refresh:
    the browsable tree is a derived view and the rest of it is still valid.
    """

    collection_path: Path
    kind: DanglingMemberKind
    member_id: str


@dataclass(frozen=True)
class BrowsableRefreshResult:
    """Result of a browsable refresh run."""

    albums_rendered: int = 0
    collections_rendered: int = 0
    symlinks_created: int = 0
    errors: tuple[BrowsableRefreshError, ...] = ()
    dangling_members: tuple[DanglingMember, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Safety check
# ---------------------------------------------------------------------------


def _validate_browsable_dir(browsable_dir: Path) -> BrowsableRefreshError | None:
    """Validate that browsable/ only contains directories and symlinks.

    Returns an error naming the first regular file found, else ``None``.
    """
    regular_file = next(
        (
            path
            for path in (
                browsable_dir.rglob("*") if browsable_dir.exists() else iter(())
            )
            if path.is_file() and not path.is_symlink()
        ),
        None,
    )
    return (
        BrowsableRefreshError(BrowsableRefreshErrorKind.REGULAR_FILE, regular_file)
        if regular_file is not None
        else None
    )


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
    media_sources: tuple[MediaSource, ...]


@dataclass(frozen=True)
class _CollectionEntry:
    """Collection info needed for rendering."""

    path: Path
    collection_id: str
    name: str
    private: bool
    year: str | None
    strategy: CollectionStrategy
    album_ids: tuple[str, ...]
    collection_ids: tuple[str, ...]
    image_ids: tuple[str, ...]
    video_ids: tuple[str, ...]


@dataclass(frozen=True)
class _MediaLocation:
    """Where a media item's browsable files live."""

    album_path: Path
    media_source: MediaSource
    key: str

    def matches(self, filename: str) -> bool:
        """Whether *filename* belongs to this item, by its source's key rule.

        The rule follows the media source type, not the filename: a std
        source may hold ``IMG_1234.JPG`` files, which are keyed by stem.
        """
        return self.media_source.key_fn(filename) == self.key


type _DirPicker = Callable[[MediaSource], str]


def _image_dir(ms: MediaSource) -> str:
    return ms.jpg_dir


def _video_dir(ms: MediaSource) -> str:
    return ms.vid_dir


# ---------------------------------------------------------------------------
# Gallery scanning
# ---------------------------------------------------------------------------


def _try_scan_album(album_dir: Path) -> _AlbumEntry | BrowsableRefreshError:
    """Scan a single album. Returns its entry or why it cannot be rendered."""
    meta = read_or_none(load_album_metadata, album_dir)
    parsed = parse_album_name(album_dir.name)
    if meta is None:
        return BrowsableRefreshError(
            BrowsableRefreshErrorKind.ALBUM_MISSING_METADATA, album_dir
        )
    if parsed is None:
        return BrowsableRefreshError(
            BrowsableRefreshErrorKind.ALBUM_UNPARSEABLE_NAME, album_dir
        )
    return _AlbumEntry(
        path=album_dir,
        album_id=meta.id,
        name=album_dir.name,
        private=parsed.private,
        # Every date format starts with YYYY.
        year=parsed.date[:4],
        media_sources=tuple(discover_media_sources(album_dir)),
    )


def _build_media_locations(album: _AlbumEntry) -> dict[str, _MediaLocation]:
    """Build media ID → browsable file location mappings for one album."""
    media_meta = load_media_metadata(album.path)
    ms_by_name = {ms.name: ms for ms in album.media_sources}
    return (
        {
            mid: _MediaLocation(album_path=album.path, media_source=ms, key=key)
            for source_name, source in media_meta.media_sources.items()
            for ms in [ms_by_name.get(source_name)]
            if ms is not None
            for mid, key in [*source.images.items(), *source.videos.items()]
        }
        if media_meta is not None
        else {}
    )


def _scan_album_entries(
    gallery_dir: Path,
) -> tuple[
    dict[str, _AlbumEntry],
    dict[str, _MediaLocation],
    tuple[BrowsableRefreshError, ...],
]:
    """Scan albums and build album + media location lookups."""
    results = [_try_scan_album(d) for d in discover_albums(gallery_dir / ALBUMS_DIR)]
    albums = {r.album_id: r for r in results if isinstance(r, _AlbumEntry)}
    media_locations = {
        mid: loc
        for album in albums.values()
        for mid, loc in _build_media_locations(album).items()
    }
    errors = tuple(r for r in results if isinstance(r, BrowsableRefreshError))
    return albums, media_locations, errors


def _collection_entry(col_dir: Path, meta: CollectionMetadata) -> _CollectionEntry:
    return _CollectionEntry(
        path=col_dir,
        collection_id=meta.id,
        name=col_dir.name,
        private=parse_collection_name(col_dir.name).private,
        year=parse_collection_year(col_dir.name),
        strategy=meta.strategy,
        album_ids=tuple(meta.albums),
        collection_ids=tuple(meta.collections),
        image_ids=tuple(meta.images),
        video_ids=tuple(meta.videos),
    )


def _scan_collection_entries(
    gallery_dir: Path,
) -> tuple[dict[str, _CollectionEntry], tuple[BrowsableRefreshError, ...]]:
    """Scan collections and build collection lookup."""
    loaded = [
        (col_dir, read_or_none(load_collection_metadata, col_dir))
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
    ]
    return (
        {
            meta.id: _collection_entry(col_dir, meta)
            for col_dir, meta in loaded
            if meta is not None
        },
        tuple(
            BrowsableRefreshError(
                BrowsableRefreshErrorKind.COLLECTION_UNREADABLE_METADATA, col_dir
            )
            for col_dir, meta in loaded
            if meta is None
        ),
    )


def _dangling_members(
    collections: Mapping[str, _CollectionEntry],
    albums: Mapping[str, _AlbumEntry],
    media_locations: Mapping[str, _MediaLocation],
) -> tuple[DanglingMember, ...]:
    """Member IDs of every collection that resolve to nothing.

    Computed once per collection (not per rendering, since a sub-collection
    renders once per parent) so each dangling ID is reported once.
    """
    member_lists: list[
        tuple[
            DanglingMemberKind, Callable[[_CollectionEntry], tuple[str, ...]], Mapping
        ]
    ] = [
        (DanglingMemberKind.ALBUM, lambda c: c.album_ids, albums),
        (DanglingMemberKind.COLLECTION, lambda c: c.collection_ids, collections),
        (DanglingMemberKind.IMAGE, lambda c: c.image_ids, media_locations),
        (DanglingMemberKind.VIDEO, lambda c: c.video_ids, media_locations),
    ]
    return tuple(
        DanglingMember(collection_path=col.path, kind=kind, member_id=member_id)
        for col in collections.values()
        for kind, members, known in member_lists
        for member_id in members(col)
        if member_id not in known
    )


# ---------------------------------------------------------------------------
# Symlink helpers
# ---------------------------------------------------------------------------


def _make_relative_symlink(target: Path, link: Path) -> None:
    """Create a relative symlink from *link* pointing to *target*."""
    link.parent.mkdir(parents=True, exist_ok=True)
    rel_target = os.path.relpath(target, link.parent)
    os.symlink(rel_target, link)


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
        for d in [
            *(ms.jpg_dir for ms in album.media_sources),
            *(ms.vid_dir for ms in album.media_sources),
        ]
    )


# ---------------------------------------------------------------------------
# Collection rendering — media helpers
# ---------------------------------------------------------------------------


def _matching_files(loc: _MediaLocation, pick_dir: _DirPicker) -> list[Path]:
    """The browsable files of one media item in the directory *pick_dir* names."""
    browsable_dir = loc.album_path / pick_dir(loc.media_source)
    return (
        [f for f in browsable_dir.iterdir() if f.is_file() and loc.matches(f.name)]
        if browsable_dir.is_dir()
        else []
    )


def _render_media_files(
    media_ids: tuple[str, ...],
    media_locations: Mapping[str, _MediaLocation],
    target_subdir: Path,
    pick_dir: _DirPicker,
) -> int:
    """Symlink individual media files into target_subdir. Returns count.

    Symlinks are prefixed with the album name and media source to
    prevent collisions when multiple albums or sources contain files
    with the same name (e.g. ``IMG_0001.jpg``).  The resulting name
    is ``{album_name} - {media_source} - {filename}``.
    """
    links = [
        (
            f,
            target_subdir
            / f"{loc.album_path.name} - {loc.media_source.name} - {f.name}",
        )
        for mid in media_ids
        for loc in [media_locations.get(mid)]
        if loc is not None
        for f in _matching_files(loc, pick_dir)
    ]
    for target, link in links:
        _make_relative_symlink(target, link)
    return len(links)


# ---------------------------------------------------------------------------
# Collection rendering (recursive)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Gallery:
    """Everything collection rendering looks members up in."""

    albums: Mapping[str, _AlbumEntry]
    collections: Mapping[str, _CollectionEntry]
    media_locations: Mapping[str, _MediaLocation]


def _render_collection(
    collection: _CollectionEntry,
    target_dir: Path,
    gallery: _Gallery,
    visited: frozenset[str],
) -> tuple[int, tuple[BrowsableRefreshError, ...]]:
    """Render a collection recursively. Returns (symlink_count, errors)."""
    if collection.collection_id in visited:
        return 0, (
            BrowsableRefreshError(
                BrowsableRefreshErrorKind.CYCLE,
                collection.path,
                collection_id=collection.collection_id,
            ),
        )
    col_target = target_dir / collection.name
    album_count = sum(
        _render_album(album, col_target / "albums")
        for album_id in collection.album_ids
        for album in [gallery.albums.get(album_id)]
        if album is not None
    )
    sub_count, sub_errors = _render_collections(
        [gallery.collections.get(cid) for cid in collection.collection_ids],
        lambda _: col_target / "collections",
        gallery,
        visited | {collection.collection_id},
    )
    image_count = _render_media_files(
        collection.image_ids, gallery.media_locations, col_target / "images", _image_dir
    )
    video_count = _render_media_files(
        collection.video_ids, gallery.media_locations, col_target / "videos", _video_dir
    )
    return album_count + sub_count + image_count + video_count, sub_errors


def _render_collections(
    collections: list[_CollectionEntry | None],
    target_for: Callable[[_CollectionEntry], Path],
    gallery: _Gallery,
    visited: frozenset[str],
) -> tuple[int, tuple[BrowsableRefreshError, ...]]:
    """Render several collections; sum their symlinks and gather their errors.

    ``None`` entries (dangling member IDs, reported separately) are skipped.
    """
    rendered = [
        _render_collection(col, target_for(col), gallery, visited)
        for col in collections
        if col is not None
    ]
    return (
        sum(count for count, _ in rendered),
        tuple(e for _, errors in rendered for e in errors),
    )


# ---------------------------------------------------------------------------
# Top-level rendering
# ---------------------------------------------------------------------------


def _collection_bucket(col: _CollectionEntry) -> tuple[str, str]:
    """Determine the bucket path for a collection."""
    match col.strategy:
        case CollectionStrategy.CHAPTER:
            return ("by-chapter", "")
        case _:
            return ("by-year", col.year) if col.year is not None else ("all-time", "")


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


def _render_all(
    gallery: _Gallery, browsable_dir: Path
) -> tuple[int, tuple[BrowsableRefreshError, ...]]:
    """Render every album and collection. Returns (symlinks, errors)."""
    album_symlinks = sum(
        _render_album(album, _album_target_dir(browsable_dir, album))
        for album in gallery.albums.values()
    )
    col_symlinks, errors = _render_collections(
        list(gallery.collections.values()),
        lambda col: _collection_target_dir(browsable_dir, col),
        gallery,
        frozenset(),
    )
    return album_symlinks + col_symlinks, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def refresh_browsable(
    gallery_dir: Path,
    *,
    dry_run: bool = False,
) -> BrowsableRefreshResult:
    """Render the browsable directory structure.

    1. Validate the existing browsable/ directory and scan the gallery
    2. Remove the existing browsable/ directory
    3. Render albums by year under public/private
    4. Render collections by year/chapter/all-time under public/private

    Unreadable albums or collections abort before anything is removed;
    dangling collection members are reported and skipped.
    """
    browsable_dir = gallery_dir / BROWSABLE_DIR
    safety_error = _validate_browsable_dir(browsable_dir)
    if safety_error is not None:
        return BrowsableRefreshResult(errors=(safety_error,))

    albums, media_locations, album_errors = _scan_album_entries(gallery_dir)
    collections, collection_errors = _scan_collection_entries(gallery_dir)
    if album_errors or collection_errors:
        return BrowsableRefreshResult(errors=(*album_errors, *collection_errors))

    gallery = _Gallery(albums, collections, media_locations)
    dangling = _dangling_members(collections, albums, media_locations)
    if dry_run:
        return BrowsableRefreshResult(
            albums_rendered=len(albums),
            collections_rendered=len(collections),
            dangling_members=dangling,
        )

    if browsable_dir.exists():
        shutil.rmtree(browsable_dir)
    symlinks, render_errors = _render_all(gallery, browsable_dir)
    return BrowsableRefreshResult(
        albums_rendered=len(albums),
        collections_rendered=len(collections),
        symlinks_created=symlinks,
        errors=render_errors,
        dangling_members=dangling,
    )
