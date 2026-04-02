"""Album and gallery statistics computation.

Computes disk usage, file counts, and content breakdowns for albums and
galleries. All results are frozen dataclasses suitable for display via
the output formatting layer.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from ..naming import parse_album_name
from ..store.media_sources_discovery import discover_media_sources
from .aggregate import aggregate_media_sources, merge_aggregates
from .models import (
    AlbumStats,
    AggregateStats,
    FormatStats,
    GalleryStats,
    MediaSourceStats,
    RoleBreakdown,
    SizeStats,
    YearStats,
)
from .scan import (
    categorize_size_stats,
    count_unique_pictures,
    count_unique_videos,
    tag_format_role,
)

__all__ = [
    "AggregateStats",
    "AlbumStats",
    "FormatStats",
    "GalleryStats",
    "MediaSourceStats",
    "RoleBreakdown",
    "SizeStats",
    "YearStats",
    "compute_album_stats",
    "compute_gallery_stats",
    "compute_media_source_stats",
    "gallery_stats_from_album_stats",
]

_ZERO_SIZE_STATS = SizeStats(file_count=0, apparent_bytes=0, on_disk_bytes=0)


# ---------------------------------------------------------------------------
# Per-media-source computation
# ---------------------------------------------------------------------------


def compute_media_source_stats(
    album_dir: Path,
    ms: "MediaSourceStats | object",
    seen_inodes: set[tuple[int, int]],
) -> MediaSourceStats:
    """Compute stats for a single media source within an album."""
    from ..store.protocol import MediaSource

    assert isinstance(ms, MediaSource)

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

    from .aggregate import merge_size_stats, merge_format_stats

    # Archive directories (iOS and std sources with archive on disk)
    has_archive = (album_dir / ms.archive_dir).is_dir()
    if has_archive:
        archive_dirs = [
            ms.orig_img_dir,
            ms.edit_img_dir,
            ms.orig_vid_dir,
            ms.edit_vid_dir,
        ]
        archive_parts: list[SizeStats] = []
        for subdir in archive_dirs:
            imgs, vids, scs, fmts = categorize_size_stats(
                album_dir / subdir, seen_inodes
            )
            archive_parts.append(merge_size_stats([imgs, vids, scs]))
            archive_images = merge_size_stats([archive_images, imgs])
            archive_videos = merge_size_stats([archive_videos, vids])
            archive_sidecars = merge_size_stats([archive_sidecars, scs])
            all_formats.append(tag_format_role(fmts, role="archive"))
        archive_stats = merge_size_stats(archive_parts)

    # Original / browsable directories ({name}-img/, {name}-vid/)
    original_parts: list[SizeStats] = []
    for subdir in (ms.img_dir, ms.vid_dir):
        imgs, vids, scs, fmts = categorize_size_stats(album_dir / subdir, seen_inodes)
        original_parts.append(merge_size_stats([imgs, vids, scs]))
        original_images = merge_size_stats([original_images, imgs])
        original_videos = merge_size_stats([original_videos, vids])
        original_sidecars = merge_size_stats([original_sidecars, scs])
        all_formats.append(fmts)  # browsable: neither archive nor derived
    original_stats = merge_size_stats(original_parts)

    # Derived directory ({name}-jpg/)
    imgs, vids, scs, fmts = categorize_size_stats(album_dir / ms.jpg_dir, seen_inodes)
    derived_stats = merge_size_stats([imgs, vids, scs])
    derived_images = merge_size_stats([derived_images, imgs])
    derived_videos = merge_size_stats([derived_videos, vids])
    derived_sidecars = merge_size_stats([derived_sidecars, scs])
    all_formats.append(tag_format_role(fmts, role="derived"))

    # Build RoleBreakdowns
    all_images = merge_size_stats([archive_images, original_images, derived_images])
    all_videos = merge_size_stats([archive_videos, original_videos, derived_videos])
    all_sidecars = merge_size_stats(
        [archive_sidecars, original_sidecars, derived_sidecars]
    )

    # Unique media counts
    unique_pics = count_unique_pictures(album_dir, ms, has_archive=has_archive)
    unique_vids = count_unique_videos(album_dir, ms, has_archive=has_archive)

    total = merge_size_stats([archive_stats, original_stats, derived_stats])

    return MediaSourceStats(
        name=ms.name,
        media_source_type=ms.media_source_type,
        total=total,
        archive=archive_stats,
        original=original_stats,
        derived=derived_stats,
        unique_pictures=unique_pics,
        unique_videos=unique_vids,
        images=RoleBreakdown(
            total=all_images, archive=archive_images, derived=derived_images
        ),
        videos=RoleBreakdown(
            total=all_videos, archive=archive_videos, derived=derived_videos
        ),
        sidecars=RoleBreakdown(
            total=all_sidecars, archive=archive_sidecars, derived=derived_sidecars
        ),
        by_format=merge_format_stats(all_formats),
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
        aggregate=aggregate_media_sources(ms_stats),
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
            aggregate=merge_aggregates(aggs),
        )
        for year, aggs in sorted(year_groups.items())
    )

    return GalleryStats(
        album_count=len(album_stats_list),
        by_album=tuple(album_stats_list),
        aggregate=merge_aggregates(a.aggregate for a in album_stats_list),
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
