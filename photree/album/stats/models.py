"""Stats data model — frozen dataclasses for album and gallery statistics."""

from __future__ import annotations

from dataclasses import dataclass

from ..store.protocol import MediaSourceType
from ...collection.stats.models import GalleryCollectionStats


@dataclass(frozen=True)
class SizeStats:
    """File count and size, with inode-dedup awareness."""

    file_count: int
    apparent_bytes: int  # naive sum of st_size (counts hardlinked files multiple times)
    on_disk_bytes: int  # deduped by (st_dev, st_ino)


@dataclass(frozen=True)
class RoleBreakdown:
    """Size stats with archive/derived breakdown."""

    total: SizeStats
    archive: SizeStats
    derived: SizeStats


@dataclass(frozen=True)
class FormatStats:
    """Per-extension file statistics."""

    extension: str  # e.g. ".heic", ".mov"
    file_count: int
    apparent_bytes: int
    on_disk_bytes: int
    archive_bytes: int
    derived_bytes: int


@dataclass(frozen=True)
class MediaSourceStats:
    """Statistics for a single media source within an album."""

    name: str
    media_source_type: MediaSourceType
    total: SizeStats
    archive: SizeStats  # archive subtree (ios-{name}/ or std-{name}/); zero when absent
    original: SizeStats  # {name}-img/ + {name}-vid/
    derived: SizeStats  # {name}-jpg/
    unique_pictures: int  # unique keys in orig-img (archive) or img (browsable)
    unique_videos: int  # unique keys in orig-vid (archive) or vid (browsable)
    images: RoleBreakdown
    videos: RoleBreakdown
    sidecars: RoleBreakdown
    by_format: tuple[FormatStats, ...]


@dataclass(frozen=True)
class AggregateStats:
    """Common aggregate fields shared between album-level and gallery-level stats.

    Extracted so the same aggregation logic and output formatting code can be
    reused at both levels and for per-year breakdowns.
    """

    total: SizeStats
    archive: SizeStats
    original: SizeStats
    derived: SizeStats
    unique_pictures: int
    unique_videos: int
    images: RoleBreakdown
    videos: RoleBreakdown
    sidecars: RoleBreakdown
    by_format: tuple[FormatStats, ...]
    media_source_count: int
    by_media_source_type: tuple[tuple[MediaSourceType, int], ...]


@dataclass(frozen=True)
class AlbumStats:
    """Statistics for a single album."""

    album_name: str
    album_year: str
    by_media_source: tuple[MediaSourceStats, ...]
    aggregate: AggregateStats
    cache_storage: SizeStats | None = None


@dataclass(frozen=True)
class YearStats:
    """Gallery statistics for a single year."""

    year: str
    album_count: int
    aggregate: AggregateStats
    cache_storage: SizeStats | None = None


@dataclass(frozen=True)
class GalleryStats:
    """Aggregated statistics for an entire gallery."""

    album_count: int
    by_album: tuple[AlbumStats, ...]
    aggregate: AggregateStats
    unique_media_source_names: tuple[str, ...]
    by_year: tuple[YearStats, ...]
    collection_stats: GalleryCollectionStats | None = None
    cache_storage: SizeStats | None = None
