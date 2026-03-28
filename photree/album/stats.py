"""Album and gallery statistics computation.

Computes disk usage, file counts, and content breakdowns for albums and
galleries. All results are frozen dataclasses suitable for display via
the output formatting layer.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from ..fsprotocol import (
    IMG_EXTENSIONS,
    SIDECAR_EXTENSIONS,
    VID_EXTENSIONS,
    MediaSource,
    MediaSourceType,
    dedup_media_dict,
    discover_media_sources,
    file_ext,
    list_files,
)
from .naming import parse_album_name


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


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
    archive: SizeStats  # ios-{name}/ subtree (zero for plain)
    original: SizeStats  # {name}-img/ + {name}-vid/
    derived: SizeStats  # {name}-jpg/
    unique_pictures: int  # iOS: unique numbers in orig-img, plain: unique stems in img
    unique_videos: int  # iOS: unique numbers in orig-vid, plain: unique stems in vid
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


@dataclass(frozen=True)
class YearStats:
    """Gallery statistics for a single year."""

    year: str
    album_count: int
    aggregate: AggregateStats


@dataclass(frozen=True)
class GalleryStats:
    """Aggregated statistics for an entire gallery."""

    album_count: int
    by_album: tuple[AlbumStats, ...]
    aggregate: AggregateStats
    unique_media_source_names: tuple[str, ...]
    by_year: tuple[YearStats, ...]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ZERO_SIZE_STATS = SizeStats(file_count=0, apparent_bytes=0, on_disk_bytes=0)
_ZERO_ROLE = RoleBreakdown(
    total=_ZERO_SIZE_STATS, archive=_ZERO_SIZE_STATS, derived=_ZERO_SIZE_STATS
)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _scan_directory(
    directory: Path,
    seen_inodes: set[tuple[int, int]],
) -> tuple[SizeStats, tuple[FormatStats, ...]]:
    """Scan a single directory, returning size stats and per-format breakdown.

    Files whose ``(st_dev, st_ino)`` is already in *seen_inodes* contribute
    to ``apparent_bytes`` but not ``on_disk_bytes``.  New inodes are added
    to the set.

    Returns ``FormatStats`` with ``archive_bytes=0`` and ``derived_bytes=0``
    — the caller tags the role.
    """
    files = list_files(directory)
    if not files:
        return _ZERO_SIZE_STATS, ()

    total_apparent = 0
    total_on_disk = 0
    total_count = 0
    format_apparent: Counter[str] = Counter()
    format_on_disk: Counter[str] = Counter()
    format_count: Counter[str] = Counter()

    for filename in files:
        path = directory / filename
        st = os.stat(path)
        size = st.st_size
        ext = file_ext(filename)
        inode_key = (st.st_dev, st.st_ino)

        total_apparent += size
        total_count += 1
        format_apparent[ext] += size
        format_count[ext] += 1

        if inode_key not in seen_inodes:
            seen_inodes.add(inode_key)
            total_on_disk += size
            format_on_disk[ext] += size

    by_format = tuple(
        FormatStats(
            extension=ext,
            file_count=format_count[ext],
            apparent_bytes=amt,
            on_disk_bytes=format_on_disk[ext],
            archive_bytes=0,
            derived_bytes=0,
        )
        for ext, amt in sorted(format_apparent.items(), key=lambda kv: -kv[1])
    )
    return (
        SizeStats(
            file_count=total_count,
            apparent_bytes=total_apparent,
            on_disk_bytes=total_on_disk,
        ),
        by_format,
    )


def _categorize_size_stats(
    directory: Path,
    seen_inodes: set[tuple[int, int]],
) -> tuple[SizeStats, SizeStats, SizeStats, tuple[FormatStats, ...]]:
    """Scan a directory and split results into images / videos / sidecars.

    Returns ``(images, videos, sidecars, by_format)`` where ``FormatStats``
    have ``archive_bytes=0`` and ``derived_bytes=0``.
    """
    files = list_files(directory)
    if not files:
        return _ZERO_SIZE_STATS, _ZERO_SIZE_STATS, _ZERO_SIZE_STATS, ()

    img_apparent = img_on_disk = img_count = 0
    vid_apparent = vid_on_disk = vid_count = 0
    sc_apparent = sc_on_disk = sc_count = 0
    format_apparent: Counter[str] = Counter()
    format_on_disk: Counter[str] = Counter()
    format_count: Counter[str] = Counter()

    for filename in files:
        path = directory / filename
        st = os.stat(path)
        size = st.st_size
        ext = file_ext(filename)
        inode_key = (st.st_dev, st.st_ino)
        is_new = inode_key not in seen_inodes
        if is_new:
            seen_inodes.add(inode_key)

        format_apparent[ext] += size
        format_count[ext] += 1

        if ext in IMG_EXTENSIONS:
            img_apparent += size
            img_count += 1
            if is_new:
                img_on_disk += size
                format_on_disk[ext] += size
        elif ext in VID_EXTENSIONS:
            vid_apparent += size
            vid_count += 1
            if is_new:
                vid_on_disk += size
                format_on_disk[ext] += size
        elif ext in SIDECAR_EXTENSIONS:
            sc_apparent += size
            sc_count += 1
            if is_new:
                sc_on_disk += size
                format_on_disk[ext] += size
        else:
            if is_new:
                format_on_disk[ext] += size

    by_format = tuple(
        FormatStats(
            extension=ext,
            file_count=format_count[ext],
            apparent_bytes=amt,
            on_disk_bytes=format_on_disk[ext],
            archive_bytes=0,
            derived_bytes=0,
        )
        for ext, amt in sorted(format_apparent.items(), key=lambda kv: -kv[1])
    )
    return (
        SizeStats(
            file_count=img_count, apparent_bytes=img_apparent, on_disk_bytes=img_on_disk
        ),
        SizeStats(
            file_count=vid_count, apparent_bytes=vid_apparent, on_disk_bytes=vid_on_disk
        ),
        SizeStats(
            file_count=sc_count, apparent_bytes=sc_apparent, on_disk_bytes=sc_on_disk
        ),
        by_format,
    )


def _tag_format_role(
    fmts: tuple[FormatStats, ...],
    *,
    role: str,
) -> tuple[FormatStats, ...]:
    """Set archive_bytes or derived_bytes on format stats based on role."""
    match role:
        case "archive":
            return tuple(
                FormatStats(
                    extension=fs.extension,
                    file_count=fs.file_count,
                    apparent_bytes=fs.apparent_bytes,
                    on_disk_bytes=fs.on_disk_bytes,
                    archive_bytes=fs.apparent_bytes,
                    derived_bytes=0,
                )
                for fs in fmts
            )
        case "derived":
            return tuple(
                FormatStats(
                    extension=fs.extension,
                    file_count=fs.file_count,
                    apparent_bytes=fs.apparent_bytes,
                    on_disk_bytes=fs.on_disk_bytes,
                    archive_bytes=0,
                    derived_bytes=fs.apparent_bytes,
                )
                for fs in fmts
            )
        case _:
            return fmts


# ---------------------------------------------------------------------------
# Unique media counting
# ---------------------------------------------------------------------------


def _count_unique_pictures_ios(album_dir: Path, ms: MediaSource) -> int:
    return len(
        dedup_media_dict(list_files(album_dir / ms.orig_img_dir), IMG_EXTENSIONS)
    )


def _count_unique_pictures_plain(album_dir: Path, ms: MediaSource) -> int:
    return len(
        {
            Path(f).stem
            for f in list_files(album_dir / ms.img_dir)
            if file_ext(f) in IMG_EXTENSIONS
        }
    )


def _count_unique_videos_ios(album_dir: Path, ms: MediaSource) -> int:
    return len(
        dedup_media_dict(list_files(album_dir / ms.orig_vid_dir), VID_EXTENSIONS)
    )


def _count_unique_videos_plain(album_dir: Path, ms: MediaSource) -> int:
    return len(
        {
            Path(f).stem
            for f in list_files(album_dir / ms.vid_dir)
            if file_ext(f) in VID_EXTENSIONS
        }
    )


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _merge_size_stats(stats: Iterable[SizeStats]) -> SizeStats:
    """Sum ``SizeStats`` fields across multiple instances."""
    fc = ab = od = 0
    for s in stats:
        fc += s.file_count
        ab += s.apparent_bytes
        od += s.on_disk_bytes
    return SizeStats(file_count=fc, apparent_bytes=ab, on_disk_bytes=od)


def _merge_role_breakdowns(breakdowns: Iterable[RoleBreakdown]) -> RoleBreakdown:
    """Sum ``RoleBreakdown`` fields across multiple instances."""
    bd_list = list(breakdowns)
    return RoleBreakdown(
        total=_merge_size_stats(b.total for b in bd_list),
        archive=_merge_size_stats(b.archive for b in bd_list),
        derived=_merge_size_stats(b.derived for b in bd_list),
    )


def _merge_format_stats(
    groups: Iterable[tuple[FormatStats, ...]],
) -> tuple[FormatStats, ...]:
    """Merge per-format stats across multiple sources, sorted by bytes desc."""
    count_by_ext: Counter[str] = Counter()
    bytes_by_ext: Counter[str] = Counter()
    on_disk_by_ext: Counter[str] = Counter()
    archive_by_ext: Counter[str] = Counter()
    derived_by_ext: Counter[str] = Counter()
    for group in groups:
        for fs in group:
            count_by_ext[fs.extension] += fs.file_count
            bytes_by_ext[fs.extension] += fs.apparent_bytes
            on_disk_by_ext[fs.extension] += fs.on_disk_bytes
            archive_by_ext[fs.extension] += fs.archive_bytes
            derived_by_ext[fs.extension] += fs.derived_bytes
    return tuple(
        FormatStats(
            extension=ext,
            file_count=count_by_ext[ext],
            apparent_bytes=amt,
            on_disk_bytes=on_disk_by_ext[ext],
            archive_bytes=archive_by_ext[ext],
            derived_bytes=derived_by_ext[ext],
        )
        for ext, amt in sorted(bytes_by_ext.items(), key=lambda kv: -kv[1])
    )


def _aggregate_media_sources(
    sources: Iterable[MediaSourceStats],
) -> AggregateStats:
    """Build an ``AggregateStats`` from per-media-source stats."""
    source_list = list(sources)
    type_counts: Counter[MediaSourceType] = Counter()
    for ms in source_list:
        type_counts[ms.media_source_type] += 1

    return AggregateStats(
        total=_merge_size_stats(ms.total for ms in source_list),
        archive=_merge_size_stats(ms.archive for ms in source_list),
        original=_merge_size_stats(ms.original for ms in source_list),
        derived=_merge_size_stats(ms.derived for ms in source_list),
        unique_pictures=sum(ms.unique_pictures for ms in source_list),
        unique_videos=sum(ms.unique_videos for ms in source_list),
        images=_merge_role_breakdowns(ms.images for ms in source_list),
        videos=_merge_role_breakdowns(ms.videos for ms in source_list),
        sidecars=_merge_role_breakdowns(ms.sidecars for ms in source_list),
        by_format=_merge_format_stats(ms.by_format for ms in source_list),
        media_source_count=len(source_list),
        by_media_source_type=tuple(sorted(type_counts.items(), key=lambda kv: kv[0])),
    )


def _merge_aggregates(aggregates: Iterable[AggregateStats]) -> AggregateStats:
    """Merge multiple ``AggregateStats`` (e.g. from albums into gallery)."""
    agg_list = list(aggregates)
    type_counts: Counter[MediaSourceType] = Counter()
    for a in agg_list:
        for mst, count in a.by_media_source_type:
            type_counts[mst] += count

    return AggregateStats(
        total=_merge_size_stats(a.total for a in agg_list),
        archive=_merge_size_stats(a.archive for a in agg_list),
        original=_merge_size_stats(a.original for a in agg_list),
        derived=_merge_size_stats(a.derived for a in agg_list),
        unique_pictures=sum(a.unique_pictures for a in agg_list),
        unique_videos=sum(a.unique_videos for a in agg_list),
        images=_merge_role_breakdowns(a.images for a in agg_list),
        videos=_merge_role_breakdowns(a.videos for a in agg_list),
        sidecars=_merge_role_breakdowns(a.sidecars for a in agg_list),
        by_format=_merge_format_stats(a.by_format for a in agg_list),
        media_source_count=sum(a.media_source_count for a in agg_list),
        by_media_source_type=tuple(sorted(type_counts.items(), key=lambda kv: kv[0])),
    )


# ---------------------------------------------------------------------------
# Per-media-source computation
# ---------------------------------------------------------------------------


def compute_media_source_stats(
    album_dir: Path,
    ms: MediaSource,
    seen_inodes: set[tuple[int, int]],
) -> MediaSourceStats:
    """Compute stats for a single media source within an album."""
    # Per-role accumulators for images/videos/sidecars
    archive_images = _ZERO_SIZE_STATS
    archive_videos = _ZERO_SIZE_STATS
    archive_sidecars = _ZERO_SIZE_STATS
    original_images = _ZERO_SIZE_STATS
    original_videos = _ZERO_SIZE_STATS
    original_sidecars = _ZERO_SIZE_STATS
    derived_images = _ZERO_SIZE_STATS
    derived_videos = _ZERO_SIZE_STATS
    derived_sidecars = _ZERO_SIZE_STATS

    all_formats: list[tuple[FormatStats, ...]] = []

    archive_stats = _ZERO_SIZE_STATS
    original_stats = _ZERO_SIZE_STATS
    derived_stats = _ZERO_SIZE_STATS

    # Archive directories (iOS only)
    if ms.is_ios:
        archive_dirs = [
            ms.orig_img_dir,
            ms.edit_img_dir,
            ms.orig_vid_dir,
            ms.edit_vid_dir,
        ]
        archive_parts: list[SizeStats] = []
        for subdir in archive_dirs:
            imgs, vids, scs, fmts = _categorize_size_stats(
                album_dir / subdir, seen_inodes
            )
            archive_parts.append(_merge_size_stats([imgs, vids, scs]))
            archive_images = _merge_size_stats([archive_images, imgs])
            archive_videos = _merge_size_stats([archive_videos, vids])
            archive_sidecars = _merge_size_stats([archive_sidecars, scs])
            all_formats.append(_tag_format_role(fmts, role="archive"))
        archive_stats = _merge_size_stats(archive_parts)

    # Original / browsable directories ({name}-img/, {name}-vid/)
    original_parts: list[SizeStats] = []
    for subdir in (ms.img_dir, ms.vid_dir):
        imgs, vids, scs, fmts = _categorize_size_stats(album_dir / subdir, seen_inodes)
        original_parts.append(_merge_size_stats([imgs, vids, scs]))
        original_images = _merge_size_stats([original_images, imgs])
        original_videos = _merge_size_stats([original_videos, vids])
        original_sidecars = _merge_size_stats([original_sidecars, scs])
        all_formats.append(fmts)  # browsable: neither archive nor derived
    original_stats = _merge_size_stats(original_parts)

    # Derived directory ({name}-jpg/)
    imgs, vids, scs, fmts = _categorize_size_stats(album_dir / ms.jpg_dir, seen_inodes)
    derived_stats = _merge_size_stats([imgs, vids, scs])
    derived_images = _merge_size_stats([derived_images, imgs])
    derived_videos = _merge_size_stats([derived_videos, vids])
    derived_sidecars = _merge_size_stats([derived_sidecars, scs])
    all_formats.append(_tag_format_role(fmts, role="derived"))

    # Build RoleBreakdowns
    all_images = _merge_size_stats([archive_images, original_images, derived_images])
    all_videos = _merge_size_stats([archive_videos, original_videos, derived_videos])
    all_sidecars = _merge_size_stats(
        [archive_sidecars, original_sidecars, derived_sidecars]
    )

    # Unique media counts
    match ms.media_source_type:
        case MediaSourceType.IOS:
            unique_pictures = _count_unique_pictures_ios(album_dir, ms)
            unique_videos = _count_unique_videos_ios(album_dir, ms)
        case MediaSourceType.PLAIN:
            unique_pictures = _count_unique_pictures_plain(album_dir, ms)
            unique_videos = _count_unique_videos_plain(album_dir, ms)

    total = _merge_size_stats([archive_stats, original_stats, derived_stats])

    return MediaSourceStats(
        name=ms.name,
        media_source_type=ms.media_source_type,
        total=total,
        archive=archive_stats,
        original=original_stats,
        derived=derived_stats,
        unique_pictures=unique_pictures,
        unique_videos=unique_videos,
        images=RoleBreakdown(
            total=all_images, archive=archive_images, derived=derived_images
        ),
        videos=RoleBreakdown(
            total=all_videos, archive=archive_videos, derived=derived_videos
        ),
        sidecars=RoleBreakdown(
            total=all_sidecars, archive=archive_sidecars, derived=derived_sidecars
        ),
        by_format=_merge_format_stats(all_formats),
    )


# ---------------------------------------------------------------------------
# Per-album computation
# ---------------------------------------------------------------------------


def _extract_year(album_name: str) -> str | None:
    """Extract the start year from an album directory name.

    Returns ``None`` when the name cannot be parsed.
    """
    parsed = parse_album_name(album_name)
    return parsed.date[:4] if parsed is not None else None


def compute_album_stats(album_dir: Path) -> AlbumStats:
    """Compute stats for a single album.

    Raises :class:`ValueError` when the album name cannot be parsed.
    """
    album_name = album_dir.name
    year = _extract_year(album_name)
    if year is None:
        raise ValueError(
            f'Album name "{album_name}" cannot be parsed. '
            f"Run photree album check to identify naming issues."
        )

    media_sources = discover_media_sources(album_dir)
    seen_inodes: set[tuple[int, int]] = set()

    ms_stats = tuple(
        compute_media_source_stats(album_dir, ms, seen_inodes) for ms in media_sources
    )

    return AlbumStats(
        album_name=album_name,
        album_year=year,
        by_media_source=ms_stats,
        aggregate=_aggregate_media_sources(ms_stats),
    )


# ---------------------------------------------------------------------------
# Gallery computation
# ---------------------------------------------------------------------------


def gallery_stats_from_album_stats(
    album_stats_list: list[AlbumStats],
) -> GalleryStats:
    """Build ``GalleryStats`` from pre-computed per-album stats.

    Useful when the caller drives the per-album loop (e.g. for progress
    reporting) and has already collected ``AlbumStats`` instances.
    """
    all_ms_names: set[str] = set()
    for a in album_stats_list:
        for ms in a.by_media_source:
            all_ms_names.add(ms.name)

    # Year breakdown
    year_groups: dict[str, list[AggregateStats]] = {}
    year_album_counts: Counter[str] = Counter()
    for a in album_stats_list:
        year_groups.setdefault(a.album_year, []).append(a.aggregate)
        year_album_counts[a.album_year] += 1

    by_year = tuple(
        YearStats(
            year=year,
            album_count=year_album_counts[year],
            aggregate=_merge_aggregates(aggs),
        )
        for year, aggs in sorted(year_groups.items())
    )

    return GalleryStats(
        album_count=len(album_stats_list),
        by_album=tuple(album_stats_list),
        aggregate=_merge_aggregates(a.aggregate for a in album_stats_list),
        unique_media_source_names=tuple(sorted(all_ms_names)),
        by_year=by_year,
    )


def compute_gallery_stats(
    albums: list[Path],
    *,
    on_album_done: Callable[[str], None] | None = None,
) -> GalleryStats:
    """Compute aggregated stats for a set of albums.

    Raises :class:`ValueError` when any album name cannot be parsed.
    """
    album_stats_list: list[AlbumStats] = []

    for album_dir in albums:
        stats = compute_album_stats(album_dir)
        album_stats_list.append(stats)
        if on_album_done is not None:
            on_album_done(album_dir.name)

    return gallery_stats_from_album_stats(album_stats_list)
