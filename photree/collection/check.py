"""
Collection validation checks.

Validates:
- The members/lifecycle/strategy combination is a valid one
- All member IDs (album, collection, image, video) exist in the gallery
- Date range covers the min/max dates of contained albums/collections
- Smart collections hold no images or videos
- Chapter collections do not overlap other chapters
- The private tag is viral: non-private collections hold no private
  members, and private smart collections only private ones
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from photree.album.naming import ParsedAlbumName, parse_album_name
from photree.album.store.album_discovery import discover_gallery_albums
from photree.album.store.media_metadata import MediaMetadata, load_media_metadata
from photree.album.store.metadata import load_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.collection.naming import ParsedCollectionName, parse_collection_name
from photree.collection.store.collection_discovery import discover_collections
from photree.collection.store.metadata import load_collection_metadata
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
    MemberType,
    is_valid_collection_config,
)
from photree.dates import date_range, range_contains, ranges_overlap
from photree.foundation.layout import COLLECTIONS_DIR
from photree.foundation.metadata_io import InvalidMetadataError


class CollectionIssueCode(StrEnum):
    """Kind of a collection check issue (a StrEnum, so it compares to str)."""

    NO_METADATA = "no-metadata"
    INVALID_METADATA = "invalid-metadata"
    INVALID_COLLECTION_CONFIG = "invalid-collection-config"
    MISSING_ALBUM = "missing-album"
    MISSING_COLLECTION = "missing-collection"
    MISSING_IMAGE = "missing-image"
    MISSING_VIDEO = "missing-video"
    DATE_NOT_COVERED = "date-not-covered"
    SMART_HAS_IMAGES = "smart-has-images"
    SMART_HAS_VIDEOS = "smart-has-videos"
    CHAPTER_DATE_OVERLAP = "chapter-date-overlap"
    PRIVATE_SMART_HAS_NON_PRIVATE_ALBUM = "private-smart-has-non-private-album"
    PRIVATE_SMART_HAS_NON_PRIVATE_COLLECTION = (
        "private-smart-has-non-private-collection"
    )
    NON_PRIVATE_HAS_PRIVATE_ALBUM = "non-private-has-private-album"
    NON_PRIVATE_HAS_PRIVATE_COLLECTION = "non-private-has-private-collection"
    NON_PRIVATE_HAS_PRIVATE_MEDIA = "non-private-has-private-media"


@dataclass(frozen=True)
class CollectionCheckIssue:
    """
    One problem found in a collection: its kind and the fields describing it.

    Fields beyond ``code`` are only set for some codes:

    - ``member_type`` and ``member_id`` (internal ID) for the member a
      MISSING_*, DATE_NOT_COVERED, PRIVATE_SMART_* or NON_PRIVATE_* issue is about
    - ``member_date`` and ``collection_date`` for DATE_NOT_COVERED
    - ``collection_date``, ``other_chapter`` (its directory name) and
      ``other_date`` for CHAPTER_DATE_OVERLAP
    - ``count`` for SMART_HAS_IMAGES and SMART_HAS_VIDEOS
    - ``reason`` for INVALID_METADATA
    - ``config`` (members, lifecycle, strategy) for INVALID_COLLECTION_CONFIG

    The message is rendered by :mod:`photree.collection.output`.
    """

    code: CollectionIssueCode
    member_type: MemberType | None = None
    member_id: str | None = None
    member_date: str | None = None
    collection_date: str | None = None
    other_chapter: str | None = None
    other_date: str | None = None
    count: int = 0
    reason: str | None = None
    config: tuple[CollectionMembers, CollectionLifecycle, CollectionStrategy] | None = (
        None
    )


@dataclass(frozen=True)
class CollectionCheckResult:
    """The issues found in one collection directory."""

    collection_dir: Path
    issues: tuple[CollectionCheckIssue, ...]

    @property
    def success(self) -> bool:
        """Whether the collection has no issues."""
        return len(self.issues) == 0


@dataclass(frozen=True)
class _ChapterRange:
    """Date range of a chapter collection, for the gallery-wide overlap check."""

    dir_name: str
    date: str
    start: date
    end: date  # inclusive


@dataclass(frozen=True)
class _GalleryLookup:
    album_ids: frozenset[str]
    album_dates: Mapping[str, str]  # album_id → date string
    album_private: Mapping[str, bool]  # album_id → private flag
    collection_ids: frozenset[str]
    collection_dates: Mapping[str, str | None]  # collection_id → date or None
    collection_private: Mapping[str, bool]  # collection_id → private flag
    image_ids: frozenset[str]
    video_ids: frozenset[str]
    # media_id → album_id (for checking if media comes from a private album)
    media_album: Mapping[str, str]
    # collection_id → range, for every dated chapter in the gallery. Built
    # gallery-wide (not per year directory) so chapters filed under different
    # ``collections/YYYY/`` directories are still compared with each other.
    chapters: Mapping[str, _ChapterRange]
    # Albums whose album or media metadata cannot be read: what they hold is
    # missing from the lookup, so a member they hold may read as missing.
    unreadable_albums: tuple[Path, ...] = ()


@dataclass(frozen=True)
class _AlbumEntry:
    id: str
    parsed: ParsedAlbumName | None
    media: MediaMetadata | None


@dataclass(frozen=True)
class _CollectionEntry:
    name: str
    meta: CollectionMetadata
    parsed: ParsedCollectionName


def _try_load[T](load: Callable[[Path], T | None], album_dir: Path) -> T | bool | None:
    """Return what *load* reads, ``None`` when absent, ``False`` when unreadable."""
    try:
        return load(album_dir)
    except InvalidMetadataError:
        return False


@dataclass(frozen=True)
class _ScannedAlbum:
    entry: _AlbumEntry | None  # None when the album has no readable album.yaml
    readable: bool


def _scan_album(album_dir: Path) -> _ScannedAlbum:
    meta = _try_load(load_album_metadata, album_dir)
    media = (
        _try_load(load_media_metadata, album_dir)
        if isinstance(meta, AlbumMetadata)
        else None
    )
    return _ScannedAlbum(
        entry=(
            _AlbumEntry(
                meta.id,
                parse_album_name(album_dir.name),
                media if isinstance(media, MediaMetadata) else None,
            )
            if isinstance(meta, AlbumMetadata)
            else None
        ),
        readable=meta is not False and media is not False,
    )


def _scan_albums(gallery_dir: Path) -> tuple[list[_AlbumEntry], tuple[Path, ...]]:
    """
    Return the albums that were read, and the directories of those that were not.

    An album whose metadata is corrupt is kept out of the lookup rather than
    aborting every collection check: the album's own check reports why, and
    the collection commands point the user to it.
    """
    scanned = [
        (album_dir, _scan_album(album_dir))
        for album_dir in discover_gallery_albums(gallery_dir)
    ]
    return (
        [s.entry for _, s in scanned if s.entry is not None],
        tuple(album_dir for album_dir, s in scanned if not s.readable),
    )


def _load_collection_or_none(collection_dir: Path) -> CollectionMetadata | None:
    # A corrupt collection.yaml is left out of the *lookup* only: its own
    # check_collection() reports it as an "invalid-metadata" issue, so it is
    # never silently ignored.
    try:
        return load_collection_metadata(collection_dir)
    except InvalidMetadataError:
        return None


def _scan_collections(gallery_dir: Path) -> list[_CollectionEntry]:
    return [
        _CollectionEntry(col_dir.name, meta, parse_collection_name(col_dir.name))
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
        for meta in [_load_collection_or_none(col_dir)]
        if meta is not None
    ]


def _chapter_range(collection_name: str) -> _ChapterRange | None:
    """Date range of a collection name, or ``None`` when dateless/unparseable."""
    parsed_date = parse_collection_name(collection_name).date
    rng = date_range(parsed_date) if parsed_date is not None else None
    match (parsed_date, rng):
        case (str(), (start, end)):
            return _ChapterRange(collection_name, parsed_date, start, end)
        case _:
            return None


def _media_owners(albums: list[_AlbumEntry], *, videos: bool) -> dict[str, str]:
    """Map each image (or video) ID to the ID of the album holding it."""
    return {
        mid: album.id
        for album in albums
        if album.media is not None
        for source in album.media.media_sources.values()
        for mid in (source.videos if videos else source.images)
    }


def build_gallery_lookup(gallery_dir: Path) -> _GalleryLookup:
    """
    Scan *gallery_dir* once and index what every collection check looks up.

    Reads the metadata of every album, its media and every collection, so one
    lookup can be shared by all the collections checked in the gallery. An
    album or collection whose metadata cannot be read is left out; the
    albums are listed in ``unreadable_albums``.
    """
    albums, unreadable_albums = _scan_albums(gallery_dir)
    collections = _scan_collections(gallery_dir)
    image_owners = _media_owners(albums, videos=False)
    video_owners = _media_owners(albums, videos=True)
    return _GalleryLookup(
        album_ids=frozenset(a.id for a in albums),
        album_dates={a.id: a.parsed.date for a in albums if a.parsed is not None},
        album_private={a.id: a.parsed.private for a in albums if a.parsed is not None},
        collection_ids=frozenset(c.meta.id for c in collections),
        collection_dates={c.meta.id: c.parsed.date for c in collections},
        collection_private={c.meta.id: c.parsed.private for c in collections},
        image_ids=frozenset(image_owners),
        video_ids=frozenset(video_owners),
        media_album={**image_owners, **video_owners},
        chapters={
            c.meta.id: rng
            for c in collections
            if c.meta.strategy == CollectionStrategy.CHAPTER
            for rng in [_chapter_range(c.name)]
            if rng is not None
        },
        unreadable_albums=unreadable_albums,
    )


def _check_missing_ids(
    ids: list[str],
    known: frozenset[str],
    code: CollectionIssueCode,
    member_type: MemberType,
) -> list[CollectionCheckIssue]:
    return [
        CollectionCheckIssue(code, member_type=member_type, member_id=mid)
        for mid in ids
        if mid not in known
    ]


def _check_member_existence(
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> list[CollectionCheckIssue]:
    return [
        *_check_missing_ids(
            metadata.albums,
            lookup.album_ids,
            CollectionIssueCode.MISSING_ALBUM,
            MemberType.ALBUM,
        ),
        *_check_missing_ids(
            metadata.collections,
            lookup.collection_ids,
            CollectionIssueCode.MISSING_COLLECTION,
            MemberType.COLLECTION,
        ),
        *_check_missing_ids(
            metadata.images,
            lookup.image_ids,
            CollectionIssueCode.MISSING_IMAGE,
            MemberType.IMAGE,
        ),
        *_check_missing_ids(
            metadata.videos,
            lookup.video_ids,
            CollectionIssueCode.MISSING_VIDEO,
            MemberType.VIDEO,
        ),
    ]


def _date_outside_range(member_date: str, col_start: date, col_end: date) -> bool:
    rng = date_range(member_date)
    return rng is not None and not range_contains((col_start, col_end), rng)


def _check_date_coverage(
    collection_dir: Path,
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> list[CollectionCheckIssue]:
    parsed_date = parse_collection_name(collection_dir.name).date
    # Dateless (or unparseable) collections have no range to check.
    col_range = date_range(parsed_date) if parsed_date is not None else None
    if parsed_date is None or col_range is None:
        return []
    member_dates = [
        *(
            (MemberType.ALBUM, aid, lookup.album_dates[aid])
            for aid in metadata.albums
            if aid in lookup.album_dates
        ),
        *(
            (MemberType.COLLECTION, cid, sub_date)
            for cid in metadata.collections
            for sub_date in [lookup.collection_dates.get(cid)]
            if sub_date is not None
        ),
    ]
    return [
        CollectionCheckIssue(
            CollectionIssueCode.DATE_NOT_COVERED,
            member_type=member_type,
            member_id=member_id,
            member_date=member_date,
            collection_date=parsed_date,
        )
        for member_type, member_id, member_date in member_dates
        if _date_outside_range(member_date, *col_range)
    ]


def _check_collection_config(
    metadata: CollectionMetadata,
) -> list[CollectionCheckIssue]:
    """Validate members + lifecycle + strategy combination."""
    config = (metadata.members, metadata.lifecycle, metadata.strategy)
    return (
        []
        if is_valid_collection_config(*config)
        else [
            CollectionCheckIssue(
                CollectionIssueCode.INVALID_COLLECTION_CONFIG,
                config=config,
            ),
        ]
    )


def _check_smart_no_media(
    metadata: CollectionMetadata,
) -> list[CollectionCheckIssue]:
    """Smart collections cannot contain image or video members."""
    if metadata.members != CollectionMembers.SMART:
        return []
    return [
        *(
            [
                CollectionCheckIssue(
                    CollectionIssueCode.SMART_HAS_IMAGES,
                    count=len(metadata.images),
                ),
            ]
            if metadata.images
            else []
        ),
        *(
            [
                CollectionCheckIssue(
                    CollectionIssueCode.SMART_HAS_VIDEOS,
                    count=len(metadata.videos),
                ),
            ]
            if metadata.videos
            else []
        ),
    ]


def _check_chapter_no_overlap(
    collection_dir: Path,
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> list[CollectionCheckIssue]:
    """
    Chapter collections must not overlap in date range with other chapters.

    Compares against every chapter of the gallery (``lookup.chapters``), not
    just the siblings in the same ``collections/YYYY/`` directory.
    """
    mine = (
        _chapter_range(collection_dir.name)
        if metadata.strategy == CollectionStrategy.CHAPTER
        else None
    )
    return (
        [
            CollectionCheckIssue(
                CollectionIssueCode.CHAPTER_DATE_OVERLAP,
                collection_date=mine.date,
                other_chapter=other.dir_name,
                other_date=other.date,
            )
            for other_id, other in sorted(
                lookup.chapters.items(),
                key=lambda item: item[1].dir_name,
            )
            # Sharing a single boundary day (2019-06-30 in both) is an overlap.
            if other_id != metadata.id
            and ranges_overlap((mine.start, mine.end), (other.start, other.end))
        ]
        if mine is not None
        else []
    )


def _private_smart_issues(
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> list[CollectionCheckIssue]:
    """Report private smart collection members that are not private."""
    return [
        *[
            CollectionCheckIssue(
                CollectionIssueCode.PRIVATE_SMART_HAS_NON_PRIVATE_ALBUM,
                member_type=MemberType.ALBUM,
                member_id=aid,
            )
            for aid in metadata.albums
            if aid in lookup.album_private and not lookup.album_private[aid]
        ],
        *[
            CollectionCheckIssue(
                CollectionIssueCode.PRIVATE_SMART_HAS_NON_PRIVATE_COLLECTION,
                member_type=MemberType.COLLECTION,
                member_id=cid,
            )
            for cid in metadata.collections
            if cid in lookup.collection_private and not lookup.collection_private[cid]
        ],
    ]


def _non_private_issues(
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> list[CollectionCheckIssue]:
    """Report the private members of a non-private collection."""
    return [
        *[
            CollectionCheckIssue(
                CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_ALBUM,
                member_type=MemberType.ALBUM,
                member_id=aid,
            )
            for aid in metadata.albums
            if lookup.album_private.get(aid, False)
        ],
        *[
            CollectionCheckIssue(
                CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_COLLECTION,
                member_type=MemberType.COLLECTION,
                member_id=cid,
            )
            for cid in metadata.collections
            if lookup.collection_private.get(cid, False)
        ],
        *[
            CollectionCheckIssue(
                CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_MEDIA,
                member_type=media_type,
                member_id=mid,
            )
            for media_type, media_ids in [
                (MemberType.IMAGE, metadata.images),
                (MemberType.VIDEO, metadata.videos),
            ]
            for mid in media_ids
            if mid in lookup.media_album
            and lookup.album_private.get(lookup.media_album[mid], False)
        ],
    ]


def _check_private_viral(
    collection_dir: Path,
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> list[CollectionCheckIssue]:
    """
    Enforce private tag virality.

    - Non-private collections cannot have private members (albums,
      collections, or media from private albums).
    - Smart private collections should only include private members
      (validated here; enforced during smart refresh).
    - Manual private collections may contain anything: the tag protects the
      collection, not its contents.
    """
    is_private = parse_collection_name(collection_dir.name).private
    is_smart = metadata.members == CollectionMembers.SMART
    match (is_private, is_smart):
        case (True, True):
            return _private_smart_issues(metadata, lookup)
        case (False, _):
            return _non_private_issues(metadata, lookup)
        case _:
            return []


def _load_for_check(
    collection_dir: Path,
) -> CollectionMetadata | CollectionCheckIssue:
    """Return the collection's metadata, or the issue that makes it unusable."""
    try:
        metadata = load_collection_metadata(collection_dir)
    except InvalidMetadataError as exc:
        return CollectionCheckIssue(
            CollectionIssueCode.INVALID_METADATA,
            reason=exc.reason,
        )
    return (
        metadata
        if metadata is not None
        else CollectionCheckIssue(CollectionIssueCode.NO_METADATA)
    )


def _metadata_issues(
    collection_dir: Path,
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> tuple[CollectionCheckIssue, ...]:
    return (
        *_check_collection_config(metadata),
        *_check_member_existence(metadata, lookup),
        *_check_date_coverage(collection_dir, metadata, lookup),
        *_check_smart_no_media(metadata),
        *_check_chapter_no_overlap(collection_dir, metadata, lookup),
        *_check_private_viral(collection_dir, metadata, lookup),
    )


def check_collection(
    collection_dir: Path,
    lookup: _GalleryLookup,
) -> CollectionCheckResult:
    """
    Check one collection against the gallery indexed in *lookup*.

    A missing or unreadable metadata file is reported as an issue, not raised.
    """
    match _load_for_check(collection_dir):
        case CollectionCheckIssue() as issue:
            issues: tuple[CollectionCheckIssue, ...] = (issue,)
        case metadata:
            issues = _metadata_issues(collection_dir, metadata, lookup)
    return CollectionCheckResult(collection_dir=collection_dir, issues=issues)


def check_all_collections(
    gallery_dir: Path,
    lookup: _GalleryLookup,
) -> list[CollectionCheckResult]:
    """
    Check every collection in *gallery_dir*, one result per collection directory.

    *lookup* is :func:`build_gallery_lookup` of the same gallery; the caller
    builds it so it can also report the albums the lookup could not read.
    """
    return [
        check_collection(col_dir, lookup)
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
    ]
