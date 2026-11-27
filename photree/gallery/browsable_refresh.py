"""
Render a browsable directory structure with symlinks.

Creates ``<gallery-dir>/browsable/`` with a hierarchy of symlinks
organized by visibility (public/private), type (albums/collections),
and grouping (by-year, all-time, by-chapter).

Called by ``gallery refresh`` after album and collection refresh.
"""

import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import groupby
from operator import attrgetter, itemgetter
from pathlib import Path

from photree.album.naming import parse_album_name
from photree.album.store.album_discovery import discover_gallery_albums
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.media_source import MediaSource
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.album.store.metadata import load_album_metadata
from photree.collection.naming import parse_collection_name, parse_collection_year
from photree.collection.store.collection_discovery import discover_collections
from photree.collection.store.metadata import load_collection_metadata
from photree.collection.store.protocol import CollectionMetadata, CollectionStrategy
from photree.foundation.layout import BROWSABLE_DIR, COLLECTIONS_DIR
from photree.foundation.metadata_io import read_or_none


class BrowsableRefreshErrorKind(StrEnum):
    """Why the browsable tree could not be (fully) rendered."""

    REGULAR_FILE = "regular-file"
    """``path``: a regular file inside ``browsable/`` (only links expected)."""

    ALBUM_MISSING_METADATA = "album-missing-metadata"
    """``path``: album whose ``album.yaml`` cannot be read."""

    ALBUM_UNPARSEABLE_NAME = "album-unparseable-name"
    """``path``: album whose name has no parseable date."""

    DUPLICATE_ALBUM_ID = "duplicate-album-id"
    """``album_id``: an ID several albums share; ``albums``: those albums."""

    COLLECTION_UNREADABLE_METADATA = "collection-unreadable-metadata"
    """``path``: collection whose ``collection.yaml`` cannot be read."""

    CYCLE = "cycle"
    """``path``: collection reached again through its own members."""

    LINK_COLLISION = "link-collision"
    """``path``: link that two different ``targets`` would both claim."""

    FILESYSTEM_ERROR = "filesystem-error"
    """``path``: what a failed write named; ``reason``: why. The tree is partial."""


@dataclass(frozen=True)
class BrowsableRefreshError:
    """A problem that stopped part of the browsable tree from being rendered."""

    kind: BrowsableRefreshErrorKind
    path: Path
    collection_id: str | None = None
    targets: tuple[Path, ...] = ()
    album_id: str | None = None
    albums: tuple[Path, ...] = ()
    reason: str | None = None


class DanglingMemberKind(StrEnum):
    """Which member list of a collection references an unknown ID."""

    ALBUM = "album"
    COLLECTION = "collection"
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True)
class DanglingMember:
    """
    A collection member ID that resolves to nothing in the gallery.

    Rendering skips it, so it is reported rather than failing the refresh:
    the browsable tree is a derived view and the rest of it is still valid.
    """

    collection_path: Path
    kind: DanglingMemberKind
    member_id: str


@dataclass(frozen=True)
class BrowsableRefreshResult:
    """What the browsable refresh rendered, and the errors and dangling members."""

    albums_rendered: int = 0
    collections_rendered: int = 0
    symlinks_created: int = 0
    errors: tuple[BrowsableRefreshError, ...] = ()
    dangling_members: tuple[DanglingMember, ...] = ()

    @property
    def success(self) -> bool:
        """Whether the refresh hit no error; dangling members do not count."""
        return len(self.errors) == 0


def _validate_browsable_dir(browsable_dir: Path) -> BrowsableRefreshError | None:
    """
    Validate that browsable/ only contains directories and symlinks.

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


type _DirPicker = Callable[[MediaSource], str]


def _image_dir(ms: MediaSource) -> str:
    return ms.jpg_dir


def _video_dir(ms: MediaSource) -> str:
    return ms.vid_dir


def _try_scan_album(album_dir: Path) -> _AlbumEntry | BrowsableRefreshError:
    """Scan a single album. Returns its entry or why it cannot be rendered."""
    meta = read_or_none(load_album_metadata, album_dir)
    parsed = parse_album_name(album_dir.name)
    if meta is None:
        return BrowsableRefreshError(
            BrowsableRefreshErrorKind.ALBUM_MISSING_METADATA,
            album_dir,
        )
    if parsed is None:
        return BrowsableRefreshError(
            BrowsableRefreshErrorKind.ALBUM_UNPARSEABLE_NAME,
            album_dir,
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
    """
    Scan albums and build album + media location lookups.

    Albums that share an ID (a copied album directory) are an error: only one
    of them could be rendered, and their media IDs would collide too.
    """
    results = [_try_scan_album(d) for d in discover_gallery_albums(gallery_dir)]
    entries = [r for r in results if isinstance(r, _AlbumEntry)]
    albums = {entry.album_id: entry for entry in entries}
    media_locations = {
        mid: loc
        for album in albums.values()
        for mid, loc in _build_media_locations(album).items()
    }
    errors = (
        *(r for r in results if isinstance(r, BrowsableRefreshError)),
        *_duplicate_id_errors(entries),
    )
    return albums, media_locations, errors


def _duplicate_id_errors(
    entries: list[_AlbumEntry],
) -> tuple[BrowsableRefreshError, ...]:
    """Return one error per album ID that several of *entries* share."""
    paths_by_id = {
        album_id: tuple(entry.path for entry in group)
        for album_id, group in groupby(
            sorted(entries, key=attrgetter("album_id")),
            key=attrgetter("album_id"),
        )
    }
    return tuple(
        BrowsableRefreshError(
            BrowsableRefreshErrorKind.DUPLICATE_ALBUM_ID,
            paths[0],
            album_id=album_id,
            albums=paths,
        )
        for album_id, paths in paths_by_id.items()
        if len(paths) > 1
    )


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
                BrowsableRefreshErrorKind.COLLECTION_UNREADABLE_METADATA,
                col_dir,
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
    """
    Member IDs of every collection that resolve to nothing.

    Computed once per collection (not per rendering, since a sub-collection
    renders once per parent) so each dangling ID is reported once.
    """
    member_lists: list[
        tuple[
            DanglingMemberKind,
            Callable[[_CollectionEntry], tuple[str, ...]],
            Mapping[str, object],
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


@dataclass(frozen=True)
class _Link:
    """A symlink to create: *link* pointing at *target*."""

    target: Path
    link: Path


def _make_relative_symlink(target: Path, link: Path) -> None:
    """Create a relative symlink from *link* pointing to *target*."""
    link.parent.mkdir(parents=True, exist_ok=True)
    rel_target = os.path.relpath(target, link.parent)
    Path(link).symlink_to(rel_target)


def _plan_album(album: _AlbumEntry, target_dir: Path) -> list[_Link]:
    """Plan an album's links: one per existing jpg and vid dir."""
    album_target = target_dir / album.name
    return [
        _Link(album.path / d, album_target / d)
        for d in [
            *(ms.jpg_dir for ms in album.media_sources),
            *(ms.vid_dir for ms in album.media_sources),
        ]
        if (album.path / d).is_dir()
    ]


def _files_by_key(
    browsable_dir: Path,
    media_source: MediaSource,
) -> dict[str, tuple[Path, ...]]:
    """
    Index the files of *browsable_dir* by media key, by its source's key rule.

    The rule follows the media source type, not the filename: a std source
    may hold ``IMG_1234.JPG`` files, which are keyed by stem.
    """
    keyed = sorted(
        (
            (media_source.key_fn(f.name), f)
            for f in (browsable_dir.iterdir() if browsable_dir.is_dir() else ())
            if f.is_file()
        ),
        key=itemgetter(0),
    )
    return {
        key: tuple(f for _, f in group)
        for key, group in groupby(keyed, key=itemgetter(0))
    }


class _BrowsableFiles:
    """
    The files of each album browsable directory, by media key, listed once.

    Collections pick media one ID at a time, often many from the same album,
    and a sub-collection is planned again under each parent: listing and
    stat'ing the directory per media ID would cost its size each time.
    """

    def __init__(self) -> None:
        """Start with no directory listed."""
        self._by_dir: dict[Path, dict[str, tuple[Path, ...]]] = {}

    def matching(self, loc: _MediaLocation, pick_dir: _DirPicker) -> tuple[Path, ...]:
        """Return one media item's files in the directory *pick_dir* names."""
        browsable_dir = loc.album_path / pick_dir(loc.media_source)
        if browsable_dir not in self._by_dir:
            self._by_dir[browsable_dir] = _files_by_key(
                browsable_dir,
                loc.media_source,
            )
        return self._by_dir[browsable_dir].get(loc.key, ())


def _plan_media_files(
    media_ids: tuple[str, ...],
    gallery: _Gallery,
    target_subdir: Path,
    pick_dir: _DirPicker,
) -> list[_Link]:
    """
    Plan links to individual media files in target_subdir.

    Links are prefixed with the album name and media source to
    prevent collisions when multiple albums or sources contain files
    with the same name (e.g. ``IMG_0001.jpg``).  The resulting name
    is ``{album_name} - {media_source} - {filename}``.
    """
    return [
        _Link(
            f,
            target_subdir
            / f"{loc.album_path.name} - {loc.media_source.name} - {f.name}",
        )
        for mid in media_ids
        for loc in [gallery.media_locations.get(mid)]
        if loc is not None
        for f in gallery.browsable_files.matching(loc, pick_dir)
    ]


@dataclass(frozen=True)
class _Gallery:
    """Everything collection rendering looks members up in."""

    albums: Mapping[str, _AlbumEntry]
    collections: Mapping[str, _CollectionEntry]
    media_locations: Mapping[str, _MediaLocation]
    browsable_files: _BrowsableFiles


def _plan_collection(
    collection: _CollectionEntry,
    target_dir: Path,
    gallery: _Gallery,
    visited: frozenset[str],
) -> tuple[list[_Link], tuple[BrowsableRefreshError, ...]]:
    """Plan a collection's links recursively. Returns (links, errors)."""
    if collection.collection_id in visited:
        return [], (
            BrowsableRefreshError(
                BrowsableRefreshErrorKind.CYCLE,
                collection.path,
                collection_id=collection.collection_id,
            ),
        )
    col_target = target_dir / collection.name
    album_links = [
        link
        for album_id in collection.album_ids
        for album in [gallery.albums.get(album_id)]
        if album is not None
        for link in _plan_album(album, col_target / "albums")
    ]
    sub_links, sub_errors = _plan_collections(
        [gallery.collections.get(cid) for cid in collection.collection_ids],
        lambda _: col_target / "collections",
        gallery,
        visited | {collection.collection_id},
    )
    image_links = _plan_media_files(
        collection.image_ids,
        gallery,
        col_target / "images",
        _image_dir,
    )
    video_links = _plan_media_files(
        collection.video_ids,
        gallery,
        col_target / "videos",
        _video_dir,
    )
    return [*album_links, *sub_links, *image_links, *video_links], sub_errors


def _plan_collections(
    collections: list[_CollectionEntry | None],
    target_for: Callable[[_CollectionEntry], Path],
    gallery: _Gallery,
    visited: frozenset[str],
) -> tuple[list[_Link], tuple[BrowsableRefreshError, ...]]:
    """
    Plan several collections; concatenate their links and gather their errors.

    ``None`` entries (dangling member IDs, reported separately) are skipped.
    """
    planned = [
        _plan_collection(col, target_for(col), gallery, visited)
        for col in collections
        if col is not None
    ]
    return (
        [link for links, _ in planned for link in links],
        tuple(e for _, errors in planned for e in errors),
    )


def _collection_bucket(col: _CollectionEntry) -> tuple[str, str]:
    match col.strategy:
        case CollectionStrategy.CHAPTER:
            return ("by-chapter", "")
        case _:
            return ("by-year", col.year) if col.year is not None else ("all-time", "")


def _album_target_dir(browsable_dir: Path, album: _AlbumEntry) -> Path:
    visibility = "private" if album.private else "public"
    return browsable_dir / visibility / "albums" / "by-year" / album.year


def _collection_target_dir(browsable_dir: Path, col: _CollectionEntry) -> Path:
    visibility = "private" if col.private else "public"
    bucket, sub_path = _collection_bucket(col)
    parts = [visibility, "collections", bucket, *([sub_path] if sub_path else [])]
    return browsable_dir / Path(*parts)


def _dedupe_links(
    links: list[_Link],
) -> tuple[tuple[_Link, ...], tuple[BrowsableRefreshError, ...]]:
    """
    Drop repeated links, and report a link two different targets claim.

    A repeat is expected (an album or collection listed twice among a
    collection's members) and is created once. A collision, such as two
    albums or two collections with the same name in the same place, cannot be
    rendered: creating the second link would fail half-way through the tree.
    """
    targets_by_link = {
        link: tuple(dict.fromkeys(p.target for p in group))
        for link, group in groupby(
            sorted(links, key=attrgetter("link")),
            key=attrgetter("link"),
        )
    }
    return (
        tuple(
            _Link(targets[0], link)
            for link, targets in targets_by_link.items()
            if len(targets) == 1
        ),
        tuple(
            BrowsableRefreshError(
                BrowsableRefreshErrorKind.LINK_COLLISION,
                link,
                targets=targets,
            )
            for link, targets in targets_by_link.items()
            if len(targets) > 1
        ),
    )


def _plan_all(
    gallery: _Gallery,
    browsable_dir: Path,
) -> tuple[list[_Link], tuple[BrowsableRefreshError, ...]]:
    """Plan the links of every album and collection. Returns (links, errors)."""
    album_links = [
        link
        for album in gallery.albums.values()
        for link in _plan_album(album, _album_target_dir(browsable_dir, album))
    ]
    col_links, errors = _plan_collections(
        list(gallery.collections.values()),
        lambda col: _collection_target_dir(browsable_dir, col),
        gallery,
        frozenset(),
    )
    return [*album_links, *col_links], errors


def refresh_browsable(
    gallery_dir: Path,
    *,
    dry_run: bool = False,
) -> BrowsableRefreshResult:
    """
    Render the browsable directory structure.

    1. Validate the existing browsable/ directory and scan the gallery
    2. Plan the links: albums by year, collections by year/chapter/all-time,
       each under public/private
    3. Remove the existing browsable/ directory
    4. Create the planned links (a write that fails stops here, reported as a
       ``FILESYSTEM_ERROR`` with the links created so far)

    Unreadable albums or collections, albums sharing an ID, and links two
    targets would claim, abort before anything is removed; dangling
    collection members are reported and skipped, and a member listed twice is
    rendered once.
    """
    browsable_dir = gallery_dir / BROWSABLE_DIR
    safety_error = _validate_browsable_dir(browsable_dir)
    if safety_error is not None:
        return BrowsableRefreshResult(errors=(safety_error,))

    albums, media_locations, album_errors = _scan_album_entries(gallery_dir)
    collections, collection_errors = _scan_collection_entries(gallery_dir)
    if album_errors or collection_errors:
        return BrowsableRefreshResult(errors=(*album_errors, *collection_errors))

    gallery = _Gallery(albums, collections, media_locations, _BrowsableFiles())
    dangling = _dangling_members(collections, albums, media_locations)
    planned, render_errors = _plan_all(gallery, browsable_dir)
    links, collisions = _dedupe_links(planned)
    if collisions:
        return BrowsableRefreshResult(errors=collisions, dangling_members=dangling)
    if dry_run:
        return BrowsableRefreshResult(
            albums_rendered=len(albums),
            collections_rendered=len(collections),
            dangling_members=dangling,
        )

    created, write_error = _render(browsable_dir, links)
    return BrowsableRefreshResult(
        albums_rendered=len(albums),
        collections_rendered=len(collections),
        symlinks_created=created,
        errors=(*render_errors, *([write_error] if write_error is not None else [])),
        dangling_members=dangling,
    )


def _render(
    browsable_dir: Path,
    links: tuple[_Link, ...],
) -> tuple[int, BrowsableRefreshError | None]:
    """
    Replace *browsable_dir* with *links*, stopping at the first write that fails.

    Returns how many links were created and the failure, if any: the tree is
    then partial, and the next refresh rebuilds it whole.
    """
    # Documented exception (docs/guidelines.md): per-item try/except, counting
    # the links created before a failure.
    created = 0
    try:
        if browsable_dir.exists():
            shutil.rmtree(browsable_dir)
        for planned_link in links:
            _make_relative_symlink(planned_link.target, planned_link.link)
            created += 1
    except OSError as exc:
        return created, BrowsableRefreshError(
            BrowsableRefreshErrorKind.FILESYSTEM_ERROR,
            Path(exc.filename) if exc.filename is not None else browsable_dir,
            reason=exc.strerror or str(exc),
        )
    return created, None
