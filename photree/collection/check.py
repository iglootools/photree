"""Collection validation checks.

Validates:
- All member IDs (album, collection, image, video) exist in the gallery
- Date range covers the min/max dates of contained albums/collections
- Naming convention
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..album.naming import _album_date_range, parse_album_name
from ..album.store.album_discovery import discover_albums
from ..album.store.media_metadata import load_media_metadata
from ..album.store.metadata import load_album_metadata
from ..fsprotocol import ALBUMS_DIR, COLLECTIONS_DIR
from .naming import parse_collection_name
from .store.collection_discovery import discover_collections
from .store.metadata import load_collection_metadata
from .store.protocol import (
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
    validate_collection_config,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectionCheckIssue:
    """A single check issue."""

    code: str
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
class _GalleryLookup:
    album_ids: frozenset[str]
    album_dates: dict[str, str]  # album_id → date string
    album_private: dict[str, bool]  # album_id → private flag
    collection_ids: frozenset[str]
    collection_dates: dict[str, str | None]  # collection_id → date string or None
    collection_private: dict[str, bool]  # collection_id → private flag
    image_ids: frozenset[str]
    video_ids: frozenset[str]
    # media_id → album_id (for checking if media comes from a private album)
    media_album: dict[str, str]


def build_gallery_lookup(gallery_dir: Path) -> _GalleryLookup:
    """Build a lightweight lookup for collection checks."""
    album_ids: set[str] = set()
    album_dates: dict[str, str] = {}
    album_private: dict[str, bool] = {}
    image_ids: set[str] = set()
    video_ids: set[str] = set()
    media_album: dict[str, str] = {}

    for album_dir in discover_albums(gallery_dir / ALBUMS_DIR):
        meta = load_album_metadata(album_dir)
        if meta is not None:
            album_ids.add(meta.id)
            parsed = parse_album_name(album_dir.name)
            if parsed is not None:
                album_dates[meta.id] = parsed.date
                album_private[meta.id] = parsed.private

            media_meta = load_media_metadata(album_dir)
            if media_meta is not None:
                for source in media_meta.media_sources.values():
                    for mid in source.images:
                        image_ids.add(mid)
                        media_album[mid] = meta.id
                    for mid in source.videos:
                        video_ids.add(mid)
                        media_album[mid] = meta.id

    collection_metas = [
        (col_dir, load_collection_metadata(col_dir))
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
    ]

    return _GalleryLookup(
        album_ids=frozenset(album_ids),
        album_dates=album_dates,
        album_private=album_private,
        collection_ids=frozenset(
            meta.id for _, meta in collection_metas if meta is not None
        ),
        collection_dates={
            meta.id: parse_collection_name(col_dir.name).date
            for col_dir, meta in collection_metas
            if meta is not None
        },
        collection_private={
            meta.id: parse_collection_name(col_dir.name).private
            for col_dir, meta in collection_metas
            if meta is not None
        },
        image_ids=frozenset(image_ids),
        video_ids=frozenset(video_ids),
        media_album=media_album,
    )


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _check_missing_ids(
    ids: list[str], known: frozenset[str], code: str, label: str
) -> list[CollectionCheckIssue]:
    """Check that all IDs in *ids* exist in *known*."""
    return [
        CollectionCheckIssue(code, f"{label} {mid} not found in gallery")
        for mid in ids
        if mid not in known
    ]


def _check_member_existence(
    metadata: CollectionMetadata, lookup: _GalleryLookup
) -> list[CollectionCheckIssue]:
    """Check all member IDs exist in the gallery."""
    return [
        *_check_missing_ids(
            metadata.albums, lookup.album_ids, "missing-album", "album"
        ),
        *_check_missing_ids(
            metadata.collections,
            lookup.collection_ids,
            "missing-collection",
            "collection",
        ),
        *_check_missing_ids(
            metadata.images, lookup.image_ids, "missing-image", "image"
        ),
        *_check_missing_ids(
            metadata.videos, lookup.video_ids, "missing-video", "video"
        ),
    ]


def _date_outside_range(member_date: str, col_start: date, col_end: date) -> bool:
    """Check if a member's date range falls outside the collection's range."""
    rng = _album_date_range(member_date)
    if rng is None:
        return False
    m_start, m_end = rng
    return m_start < col_start or m_end > col_end


def _check_date_coverage(
    collection_dir: Path,
    metadata: CollectionMetadata,
    lookup: _GalleryLookup,
) -> list[CollectionCheckIssue]:
    """Check collection date range covers all contained albums/collections."""
    parsed = parse_collection_name(collection_dir.name)
    if parsed.date is None:
        return []  # dateless collections have no range to check

    col_range = _album_date_range(parsed.date)
    if col_range is None:
        return []

    col_start, col_end = col_range

    return [
        # Albums outside range
        *[
            CollectionCheckIssue(
                "date-not-covered",
                f"album {aid} date {lookup.album_dates[aid]} "
                f"outside collection range {parsed.date}",
            )
            for aid in metadata.albums
            if aid in lookup.album_dates
            and _date_outside_range(lookup.album_dates[aid], col_start, col_end)
        ],
        # Sub-collections outside range
        *[
            CollectionCheckIssue(
                "date-not-covered",
                f"collection {cid} date {sub_date} "
                f"outside collection range {parsed.date}",
            )
            for cid in metadata.collections
            for sub_date in [lookup.collection_dates.get(cid)]
            if sub_date is not None
            and _date_outside_range(sub_date, col_start, col_end)
        ],
    ]


def _check_collection_config(
    metadata: CollectionMetadata,
) -> list[CollectionCheckIssue]:
    """Validate members + lifecycle + strategy combination."""
    error = validate_collection_config(
        metadata.members, metadata.lifecycle, metadata.strategy
    )
    if error is not None:
        return [CollectionCheckIssue("invalid-collection-config", error)]
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
                    "smart-has-images",
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
                    "smart-has-videos",
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
    """Chapter collections must not overlap in date range with other chapters."""
    if metadata.strategy != CollectionStrategy.CHAPTER:
        return []

    parsed = parse_collection_name(collection_dir.name)
    if parsed.date is None:
        return []

    my_range = _album_date_range(parsed.date)
    if my_range is None:
        return []

    my_start, my_end = my_range
    issues: list[CollectionCheckIssue] = []

    # Walk all collections looking for other chapters
    collections_dir = collection_dir.parent
    if collections_dir.exists():
        for col_dir in discover_collections(collections_dir):
            if col_dir == collection_dir:
                continue
            other_meta = load_collection_metadata(col_dir)
            if other_meta is None or other_meta.strategy != CollectionStrategy.CHAPTER:
                continue

            other_parsed = parse_collection_name(col_dir.name)
            if other_parsed.date is None:
                continue

            other_range = _album_date_range(other_parsed.date)
            if other_range is None:
                continue

            other_start, other_end = other_range
            if my_start < other_end and other_start < my_end:
                issues.append(
                    CollectionCheckIssue(
                        "chapter-date-overlap",
                        f"chapter date range {parsed.date} overlaps with "
                        f"chapter '{col_dir.name}' ({other_parsed.date})",
                    )
                )

    return issues


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
    """
    parsed = parse_collection_name(collection_dir.name)
    is_private = parsed.private
    is_smart = metadata.members == CollectionMembers.SMART

    if is_private and is_smart:
        # Smart + private: should only include private members
        return [
            *[
                CollectionCheckIssue(
                    "private-smart-has-non-private-album",
                    f"private smart collection contains non-private album {aid}",
                )
                for aid in metadata.albums
                if aid in lookup.album_private and not lookup.album_private[aid]
            ],
            *[
                CollectionCheckIssue(
                    "private-smart-has-non-private-collection",
                    f"private smart collection contains non-private collection {cid}",
                )
                for cid in metadata.collections
                if cid in lookup.collection_private
                and not lookup.collection_private[cid]
            ],
        ]
    elif not is_private:
        # Non-private: cannot have any private members
        return [
            *[
                CollectionCheckIssue(
                    "non-private-has-private-album",
                    f"non-private collection contains private album {aid}",
                )
                for aid in metadata.albums
                if lookup.album_private.get(aid, False)
            ],
            *[
                CollectionCheckIssue(
                    "non-private-has-private-collection",
                    f"non-private collection contains private collection {cid}",
                )
                for cid in metadata.collections
                if lookup.collection_private.get(cid, False)
            ],
            *[
                CollectionCheckIssue(
                    "non-private-has-private-media",
                    f"non-private collection contains {media_type} {mid} "
                    f"from private album",
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
    else:
        return []


def check_collection(
    collection_dir: Path,
    lookup: _GalleryLookup,
) -> CollectionCheckResult:
    """Run all checks on a single collection."""
    metadata = load_collection_metadata(collection_dir)
    if metadata is None:
        return CollectionCheckResult(
            collection_dir=collection_dir,
            issues=(
                CollectionCheckIssue("no-metadata", "missing .photree/collection.yaml"),
            ),
        )

    return CollectionCheckResult(
        collection_dir=collection_dir,
        issues=tuple(
            [
                *_check_collection_config(metadata),
                *_check_member_existence(metadata, lookup),
                *_check_date_coverage(collection_dir, metadata, lookup),
                *_check_smart_no_media(metadata),
                *_check_chapter_no_overlap(collection_dir, metadata, lookup),
                *_check_private_viral(collection_dir, metadata, lookup),
            ]
        ),
    )


def check_all_collections(
    gallery_dir: Path,
) -> list[CollectionCheckResult]:
    """Check all collections in the gallery."""
    lookup = build_gallery_lookup(gallery_dir)
    return [
        check_collection(col_dir, lookup)
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
    ]
