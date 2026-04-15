"""Aggregation helpers for merging stats across media sources and albums."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from ..store.protocol import MediaSourceType
from .models import (
    AggregateStats,
    FormatStats,
    MediaSourceStats,
    RoleBreakdown,
    SizeStats,
)


def merge_size_stats(stats: Iterable[SizeStats]) -> SizeStats:
    """Sum ``SizeStats`` fields across multiple instances."""
    fc = ab = od = 0
    for s in stats:
        fc += s.file_count
        ab += s.apparent_bytes
        od += s.on_disk_bytes
    return SizeStats(file_count=fc, apparent_bytes=ab, on_disk_bytes=od)


def merge_role_breakdowns(breakdowns: Iterable[RoleBreakdown]) -> RoleBreakdown:
    """Sum ``RoleBreakdown`` fields across multiple instances."""
    bd_list = list(breakdowns)
    return RoleBreakdown(
        total=merge_size_stats(b.total for b in bd_list),
        archive=merge_size_stats(b.archive for b in bd_list),
        derived=merge_size_stats(b.derived for b in bd_list),
    )


def merge_format_stats(
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


def aggregate_media_sources(
    sources: Iterable[MediaSourceStats],
) -> AggregateStats:
    """Build an ``AggregateStats`` from per-media-source stats."""
    source_list = list(sources)
    type_counts: Counter[MediaSourceType] = Counter()
    for ms in source_list:
        type_counts[ms.media_source_type] += 1

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
        by_media_source_type=tuple(sorted(type_counts.items(), key=lambda kv: kv[0])),
    )


def merge_aggregates(aggregates: Iterable[AggregateStats]) -> AggregateStats:
    """Merge multiple ``AggregateStats`` (e.g. from albums into gallery)."""
    agg_list = list(aggregates)
    type_counts: Counter[MediaSourceType] = Counter()
    for a in agg_list:
        for mst, count in a.by_media_source_type:
            type_counts[mst] += count

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
        by_media_source_type=tuple(sorted(type_counts.items(), key=lambda kv: kv[0])),
    )
