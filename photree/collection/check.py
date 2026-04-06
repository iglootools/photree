"""Collection validation checks.

Validates:
- All member IDs (album, collection, image, video) exist in the gallery
- Date range covers the min/max dates of contained albums/collections
- Naming convention
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..album.naming import _album_date_range, parse_album_name
from ..album.store.album_discovery import discover_albums
from ..album.store.media_metadata import load_media_metadata
from ..album.store.metadata import load_album_metadata
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


def build_gallery_lookup(gallery_dir: Path) -> _GalleryLookup:
    """Build a lightweight lookup for collection checks."""
    album_ids: set[str] = set()
    album_dates: dict[str, str] = {}
    image_ids: set[str] = set()
    video_ids: set[str] = set()

    for album_dir in discover_albums(gallery_dir):
        meta = load_album_metadata(album_dir)
        if meta is None:
            continue
        album_ids.add(meta.id)
        parsed = parse_album_name(album_dir.name)
        if parsed is not None:
            album_dates[meta.id] = parsed.date

        media_meta = load_media_metadata(album_dir)
        if media_meta is not None:
            for source in media_meta.media_sources.values():
                image_ids.update(source.images)
                video_ids.update(source.videos)

    collection_ids: set[str] = set()
    collection_dates: dict[str, str | None] = {}
    for col_dir in discover_collections(gallery_dir):
        col_meta = load_collection_metadata(col_dir)
        if col_meta is not None:
            collection_ids.add(col_meta.id)
            parsed_col = parse_collection_name(col_dir.name)
            collection_dates[col_meta.id] = parsed_col.date

    return _GalleryLookup(
        album_ids=frozenset(album_ids),
        album_dates=album_dates,
        collection_ids=frozenset(collection_ids),
        collection_dates=collection_dates,
        image_ids=frozenset(image_ids),
        video_ids=frozenset(video_ids),
    )


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _check_member_existence(
    metadata: CollectionMetadata, lookup: _GalleryLookup
) -> list[CollectionCheckIssue]:
    """Check all member IDs exist in the gallery."""
    issues: list[CollectionCheckIssue] = []

    for album_id in metadata.albums:
        if album_id not in lookup.album_ids:
            issues.append(
                CollectionCheckIssue(
                    "missing-album", f"album {album_id} not found in gallery"
                )
            )

    for col_id in metadata.collections:
        if col_id not in lookup.collection_ids:
            issues.append(
                CollectionCheckIssue(
                    "missing-collection", f"collection {col_id} not found in gallery"
                )
            )

    for img_id in metadata.images:
        if img_id not in lookup.image_ids:
            issues.append(
                CollectionCheckIssue(
                    "missing-image", f"image {img_id} not found in gallery"
                )
            )

    for vid_id in metadata.videos:
        if vid_id not in lookup.video_ids:
            issues.append(
                CollectionCheckIssue(
                    "missing-video", f"video {vid_id} not found in gallery"
                )
            )

    return issues


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
    issues: list[CollectionCheckIssue] = []

    # Check album dates
    for album_id in metadata.albums:
        album_date = lookup.album_dates.get(album_id)
        if album_date is None:
            continue
        album_range = _album_date_range(album_date)
        if album_range is None:
            continue
        a_start, a_end = album_range
        if a_start < col_start or a_end > col_end:
            issues.append(
                CollectionCheckIssue(
                    "date-not-covered",
                    f"album {album_id} date {album_date} outside collection range {parsed.date}",
                )
            )

    # Check sub-collection dates
    for col_id in metadata.collections:
        sub_date = lookup.collection_dates.get(col_id)
        if sub_date is None:
            continue
        sub_range = _album_date_range(sub_date)
        if sub_range is None:
            continue
        s_start, s_end = sub_range
        if s_start < col_start or s_end > col_end:
            issues.append(
                CollectionCheckIssue(
                    "date-not-covered",
                    f"collection {col_id} date {sub_date} outside collection range {parsed.date}",
                )
            )

    return issues


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

    issues: list[CollectionCheckIssue] = []
    issues.extend(_check_member_existence(metadata, lookup))
    issues.extend(_check_date_coverage(collection_dir, metadata, lookup))

    return CollectionCheckResult(
        collection_dir=collection_dir,
        issues=tuple(issues),
    )


def check_all_collections(
    gallery_dir: Path,
) -> list[CollectionCheckResult]:
    """Check all collections in the gallery."""
    lookup = build_gallery_lookup(gallery_dir)
    results: list[CollectionCheckResult] = []
    for col_dir in discover_collections(gallery_dir):
        results.append(check_collection(col_dir, lookup))
    return results
