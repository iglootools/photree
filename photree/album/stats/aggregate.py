"""Aggregation helpers for merging stats across media sources and albums."""

from __future__ import annotations

from collections.abc import Iterable

from .models import (
    AggregateStats,
    FormatStats,
    MediaSourceStats,
    MediaSourceTypeStats,
    RoleBreakdown,
    SizeStats,
)


def merge_size_stats(stats: Iterable[SizeStats]) -> SizeStats:
    """Sum ``SizeStats`` fields across multiple instances."""
    stats_list = list(stats)
    return SizeStats(
        file_count=sum(s.file_count for s in stats_list),
        apparent_bytes=sum(s.apparent_bytes for s in stats_list),
        on_disk_bytes=sum(s.on_disk_bytes for s in stats_list),
    )


def merge_role_breakdowns(breakdowns: Iterable[RoleBreakdown]) -> RoleBreakdown:
    """Sum ``RoleBreakdown`` fields across multiple instances."""
    bd_list = list(breakdowns)
    return RoleBreakdown(
        total=merge_size_stats(b.total for b in bd_list),
        archive=merge_size_stats(b.archive for b in bd_list),
        derived=merge_size_stats(b.derived for b in bd_list),
    )


def _merge_same_format(extension: str, stats: list[FormatStats]) -> FormatStats:
    return FormatStats(
        extension=extension,
        file_count=sum(fs.file_count for fs in stats),
        apparent_bytes=sum(fs.apparent_bytes for fs in stats),
        on_disk_bytes=sum(fs.on_disk_bytes for fs in stats),
        archive_bytes=sum(fs.archive_bytes for fs in stats),
        derived_bytes=sum(fs.derived_bytes for fs in stats),
    )


def merge_format_stats(
    groups: Iterable[tuple[FormatStats, ...]],
) -> tuple[FormatStats, ...]:
    """Merge per-format stats across multiple sources, sorted by bytes desc."""
    flat = [fs for group in groups for fs in group]
    # dict.fromkeys keeps first-seen extension order, which breaks size ties
    # the same way as before (stable sort).
    merged = [
        _merge_same_format(ext, [fs for fs in flat if fs.extension == ext])
        for ext in dict.fromkeys(fs.extension for fs in flat)
    ]
    return tuple(sorted(merged, key=lambda fs: -fs.apparent_bytes))


def media_source_type_stats(
    sources: Iterable[MediaSourceStats],
) -> tuple[MediaSourceTypeStats, ...]:
    """Per-type totals of *sources*, one entry per type present, by type."""
    source_list = list(sources)
    return tuple(
        MediaSourceTypeStats(
            media_source_type=mst,
            source_count=len(of_type),
            total=merge_size_stats(ms.total for ms in of_type),
            archive=merge_size_stats(ms.archive for ms in of_type),
            derived=merge_size_stats(ms.derived for ms in of_type),
        )
        for mst in sorted({ms.media_source_type for ms in source_list})
        if (of_type := [ms for ms in source_list if ms.media_source_type == mst])
    )


def merge_media_source_type_stats(
    groups: Iterable[tuple[MediaSourceTypeStats, ...]],
) -> tuple[MediaSourceTypeStats, ...]:
    """Merge per-type totals across albums, one entry per type, by type."""
    flat = [t for group in groups for t in group]
    return tuple(
        MediaSourceTypeStats(
            media_source_type=mst,
            source_count=sum(t.source_count for t in of_type),
            total=merge_size_stats(t.total for t in of_type),
            archive=merge_size_stats(t.archive for t in of_type),
            derived=merge_size_stats(t.derived for t in of_type),
        )
        for mst in sorted({t.media_source_type for t in flat})
        if (of_type := [t for t in flat if t.media_source_type == mst])
    )


def aggregate_media_sources(
    sources: Iterable[MediaSourceStats],
) -> AggregateStats:
    """Build an ``AggregateStats`` from per-media-source stats."""
    source_list = list(sources)
    return AggregateStats(
        total=merge_size_stats(ms.total for ms in source_list),
        archive=merge_size_stats(ms.archive for ms in source_list),
        original=merge_size_stats(ms.original for ms in source_list),
        derived=merge_size_stats(ms.derived for ms in source_list),
        unique_pictures=sum(ms.unique_pictures for ms in source_list),
        unique_videos=sum(ms.unique_videos for ms in source_list),
        unique_live_photos=sum(ms.unique_live_photos for ms in source_list),
        images=merge_role_breakdowns(ms.images for ms in source_list),
        videos=merge_role_breakdowns(ms.videos for ms in source_list),
        sidecars=merge_role_breakdowns(ms.sidecars for ms in source_list),
        by_format=merge_format_stats(ms.by_format for ms in source_list),
        media_source_count=len(source_list),
        by_media_source_type=media_source_type_stats(source_list),
    )


def merge_aggregates(aggregates: Iterable[AggregateStats]) -> AggregateStats:
    """Merge multiple ``AggregateStats`` (e.g. from albums into gallery)."""
    agg_list = list(aggregates)
    return AggregateStats(
        total=merge_size_stats(a.total for a in agg_list),
        archive=merge_size_stats(a.archive for a in agg_list),
        original=merge_size_stats(a.original for a in agg_list),
        derived=merge_size_stats(a.derived for a in agg_list),
        unique_pictures=sum(a.unique_pictures for a in agg_list),
        unique_videos=sum(a.unique_videos for a in agg_list),
        unique_live_photos=sum(a.unique_live_photos for a in agg_list),
        images=merge_role_breakdowns(a.images for a in agg_list),
        videos=merge_role_breakdowns(a.videos for a in agg_list),
        sidecars=merge_role_breakdowns(a.sidecars for a in agg_list),
        by_format=merge_format_stats(a.by_format for a in agg_list),
        media_source_count=sum(a.media_source_count for a in agg_list),
        by_media_source_type=merge_media_source_type_stats(
            a.by_media_source_type for a in agg_list
        ),
    )
