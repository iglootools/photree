"""Collection validation checks.

Validates:
- All member IDs (album, collection, image, video) exist in the gallery
- Date range covers the min/max dates of contained albums/collections
- Naming convention
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from ..album.id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
)
from ..album.naming import ParsedAlbumName, parse_album_name
from ..album.store.album_discovery import discover_albums
from ..album.store.media_metadata import MediaMetadata, load_media_metadata
from ..album.store.metadata import load_album_metadata
from ..dates import date_range, range_contains, ranges_overlap
from ..foundation.layout import ALBUMS_DIR, COLLECTIONS_DIR, PHOTREE_DIR
from ..foundation.metadata_io import InvalidMetadataError
from .id import format_collection_external_id
from .naming import ParsedCollectionName, parse_collection_name
from .store.collection_discovery import discover_collections
from .store.metadata import load_collection_metadata
from .store.protocol import (
    COLLECTION_YAML,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
    validate_collection_config,
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


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
    """A single check issue."""

    code: CollectionIssueCode
    message: str


@dataclass(frozen=True)
class CollectionCheckResult:
    """Result of checking a single collection."""

    collection_dir: Path
    issues: tuple[CollectionCheckIssue, ...]

    @property
    def success(self) -> bool:
        return len(self.issues) == 0


# ---------------------------------------------------------------------------
# Gallery index (lightweight, built once per check run)
# ---------------------------------------------------------------------------


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


def _scan_albums(gallery_dir: Path) -> list[_AlbumEntry]:
    return [
        _AlbumEntry(
            meta.id, parse_album_name(album_dir.name), load_media_metadata(album_dir)
        )
        for album_dir in discover_albums(gallery_dir / ALBUMS_DIR)
        for meta in [load_album_metadata(album_dir)]
        if meta is not None
    ]


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
    """Build a lightweight lookup for collection checks."""
    albums = _scan_albums(gallery_dir)
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
    )


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _fmt_album(aid: str) -> str:
    try:
        return format_album_external_id(aid)
    except ValueError:
        return aid


def _fmt_collection(cid: str) -> str:
    try:
        return format_collection_external_id(cid)
    except ValueError:
        return cid


def _safe_fmt(fmt: Callable[[str], str]) -> Callable[[str], str]:
    def _inner(mid: str) -> str:
        try:
            return fmt(mid)
        except ValueError:
            return mid

    return _inner


_MEDIA_FORMATTERS: dict[str, Callable[[str], str]] = {
    "album": _safe_fmt(format_album_external_id),
    "collection": _safe_fmt(format_collection_external_id),
    "image": _safe_fmt(format_image_external_id),
    "video": _safe_fmt(format_video_external_id),
}


def _check_missing_ids(
    ids: list[str], known: frozenset[str], code: CollectionIssueCode, label: str
) -> list[CollectionCheckIssue]:
    """Check that all IDs in *ids* exist in *known*."""
    fmt = _MEDIA_FORMATTERS.get(label, str)
    return [
        CollectionCheckIssue(code, f"{label} {fmt(mid)} not found in gallery")
        for mid in ids
        if mid not in known
    ]


def _check_member_existence(
    metadata: CollectionMetadata, lookup: _GalleryLookup
) -> list[CollectionCheckIssue]:
    """Check all member IDs exist in the gallery."""
    return [
        *_check_missing_ids(
            metadata.albums,
            lookup.album_ids,
            CollectionIssueCode.MISSING_ALBUM,
            "album",
        ),
        *_check_missing_ids(
            metadata.collections,
            lookup.collection_ids,
            CollectionIssueCode.MISSING_COLLECTION,
            "collection",
        ),
        *_check_missing_ids(
            metadata.images,
            lookup.image_ids,
            CollectionIssueCode.MISSING_IMAGE,
            "image",
        ),
        *_check_missing_ids(
            metadata.videos,
            lookup.video_ids,
            CollectionIssueCode.MISSING_VIDEO,
            "video",
        ),
    ]


def _date_outside_range(member_date: str, col_start: date, col_end: date) -> bool:
    """Check if a member's date range falls outside the collection's range."""
    rng = date_range(member_date)
    return rng is not None and not range_contains((col_start, col_end), rng)


def _check_date_coverage(
    collection_dir: Path,
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> list[CollectionCheckIssue]:
    """Check collection date range covers all contained albums/collections."""
    parsed_date = parse_collection_name(collection_dir.name).date
    # Dateless (or unparseable) collections have no range to check.
    col_range = date_range(parsed_date) if parsed_date is not None else None
    if parsed_date is None or col_range is None:
        return []
    member_dates = [
        *(
            (f"album {_fmt_album(aid)}", lookup.album_dates[aid])
            for aid in metadata.albums
            if aid in lookup.album_dates
        ),
        *(
            (f"collection {_fmt_collection(cid)}", sub_date)
            for cid in metadata.collections
            for sub_date in [lookup.collection_dates.get(cid)]
            if sub_date is not None
        ),
    ]
    return [
        CollectionCheckIssue(
            CollectionIssueCode.DATE_NOT_COVERED,
            f"{member} date {member_date} outside collection range {parsed_date}",
        )
        for member, member_date in member_dates
        if _date_outside_range(member_date, *col_range)
    ]


def _check_collection_config(
    metadata: CollectionMetadata,
) -> list[CollectionCheckIssue]:
    """Validate members + lifecycle + strategy combination."""
    error = validate_collection_config(
        metadata.members, metadata.lifecycle, metadata.strategy
    )
    if error is not None:
        return [
            CollectionCheckIssue(CollectionIssueCode.INVALID_COLLECTION_CONFIG, error)
        ]
    else:
        return []


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
                    f"smart collection has {len(metadata.images)} image member(s) "
                    f"— smart collections can only contain albums and collections",
                )
            ]
            if metadata.images
            else []
        ),
        *(
            [
                CollectionCheckIssue(
                    CollectionIssueCode.SMART_HAS_VIDEOS,
                    f"smart collection has {len(metadata.videos)} video member(s) "
                    f"— smart collections can only contain albums and collections",
                )
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
    """Chapter collections must not overlap in date range with other chapters.

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
                f"chapter date range {mine.date} overlaps with "
                f"chapter '{other.dir_name}' ({other.date})",
            )
            for other_id, other in sorted(
                lookup.chapters.items(), key=lambda item: item[1].dir_name
            )
            # Sharing a single boundary day (2019-06-30 in both) is an overlap.
            if other_id != metadata.id
            and ranges_overlap((mine.start, mine.end), (other.start, other.end))
        ]
        if mine is not None
        else []
    )


def _private_smart_issues(
    metadata: CollectionMetadata, lookup: _GalleryLookup
) -> list[CollectionCheckIssue]:
    """A private smart collection should only include private members."""
    return [
        *[
            CollectionCheckIssue(
                CollectionIssueCode.PRIVATE_SMART_HAS_NON_PRIVATE_ALBUM,
                "private smart collection contains non-private album "
                f"{_fmt_album(aid)}",
            )
            for aid in metadata.albums
            if aid in lookup.album_private and not lookup.album_private[aid]
        ],
        *[
            CollectionCheckIssue(
                CollectionIssueCode.PRIVATE_SMART_HAS_NON_PRIVATE_COLLECTION,
                "private smart collection contains non-private collection "
                f"{_fmt_collection(cid)}",
            )
            for cid in metadata.collections
            if cid in lookup.collection_private and not lookup.collection_private[cid]
        ],
    ]


def _non_private_issues(
    metadata: CollectionMetadata, lookup: _GalleryLookup
) -> list[CollectionCheckIssue]:
    """A non-private collection cannot have any private member."""
    return [
        *[
            CollectionCheckIssue(
                CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_ALBUM,
                f"non-private collection contains private album {_fmt_album(aid)}",
            )
            for aid in metadata.albums
            if lookup.album_private.get(aid, False)
        ],
        *[
            CollectionCheckIssue(
                CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_COLLECTION,
                "non-private collection contains private collection "
                f"{_fmt_collection(cid)}",
            )
            for cid in metadata.collections
            if lookup.collection_private.get(cid, False)
        ],
        *[
            CollectionCheckIssue(
                CollectionIssueCode.NON_PRIVATE_HAS_PRIVATE_MEDIA,
                f"non-private collection contains {media_type} "
                f"{_MEDIA_FORMATTERS.get(media_type, str)(mid)} from private album",
            )
            for media_type, media_ids in [
                ("image", metadata.images),
                ("video", metadata.videos),
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
    """Enforce private tag virality.

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
    """The collection's metadata, or the issue that makes it unusable."""
    try:
        metadata = load_collection_metadata(collection_dir)
    except InvalidMetadataError as exc:
        return CollectionCheckIssue(
            CollectionIssueCode.INVALID_METADATA,
            f"invalid {PHOTREE_DIR}/{COLLECTION_YAML}: {exc.reason}",
        )
    return (
        metadata
        if metadata is not None
        else CollectionCheckIssue(
            CollectionIssueCode.NO_METADATA, f"missing {PHOTREE_DIR}/{COLLECTION_YAML}"
        )
    )


def _metadata_issues(
    collection_dir: Path, metadata: CollectionMetadata, lookup: _GalleryLookup
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
    """Run all checks on a single collection."""
    match _load_for_check(collection_dir):
        case CollectionCheckIssue() as issue:
            issues: tuple[CollectionCheckIssue, ...] = (issue,)
        case metadata:
            issues = _metadata_issues(collection_dir, metadata, lookup)
    return CollectionCheckResult(collection_dir=collection_dir, issues=issues)


def check_all_collections(
    gallery_dir: Path,
) -> list[CollectionCheckResult]:
    """Check all collections in the gallery."""
    lookup = build_gallery_lookup(gallery_dir)
    return [
        check_collection(col_dir, lookup)
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
    ]
