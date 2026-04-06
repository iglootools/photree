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
from .store.protocol import CollectionMetadata


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
    collection_ids: frozenset[str]
    collection_dates: dict[str, str | None]  # collection_id → date string or None
    image_ids: frozenset[str]
    video_ids: frozenset[str]


def _scan_album_data(
    gallery_dir: Path,
) -> tuple[set[str], dict[str, str], set[str], set[str]]:
    """Scan albums and return (album_ids, album_dates, image_ids, video_ids)."""
    album_ids: set[str] = set()
    album_dates: dict[str, str] = {}
    image_ids: set[str] = set()
    video_ids: set[str] = set()

    for album_dir in discover_albums(gallery_dir / ALBUMS_DIR):
        meta = load_album_metadata(album_dir)
        if meta is not None:
            album_ids.add(meta.id)
            parsed = parse_album_name(album_dir.name)
            if parsed is not None:
                album_dates[meta.id] = parsed.date

            media_meta = load_media_metadata(album_dir)
            if media_meta is not None:
                for source in media_meta.media_sources.values():
                    image_ids.update(source.images)
                    video_ids.update(source.videos)

    return album_ids, album_dates, image_ids, video_ids


def build_gallery_lookup(gallery_dir: Path) -> _GalleryLookup:
    """Build a lightweight lookup for collection checks."""
    album_ids, album_dates, image_ids, video_ids = _scan_album_data(gallery_dir)

    collection_metas = [
        (col_dir, load_collection_metadata(col_dir))
        for col_dir in discover_collections(gallery_dir / COLLECTIONS_DIR)
    ]

    return _GalleryLookup(
        album_ids=frozenset(album_ids),
        album_dates=album_dates,
        collection_ids=frozenset(
            meta.id for _, meta in collection_metas if meta is not None
        ),
        collection_dates={
            meta.id: parse_collection_name(col_dir.name).date
            for col_dir, meta in collection_metas
            if meta is not None
        },
        image_ids=frozenset(image_ids),
        video_ids=frozenset(video_ids),
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
                *_check_member_existence(metadata, lookup),
                *_check_date_coverage(collection_dir, metadata, lookup),
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
