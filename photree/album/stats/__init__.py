"""Album and gallery statistics computation.

Computes disk usage, file counts, and content breakdowns for albums and
galleries. All results are frozen dataclasses suitable for display via
the output formatting layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

from ...fsprotocol import PHOTREE_DIR
from ..naming import parse_album_name
from ..store.media_source import MediaSource
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import CACHE_DIR
from .aggregate import (
    aggregate_media_sources,
    merge_aggregates,
    merge_format_stats,
    merge_role_breakdowns,
    merge_size_stats,
)
from .models import (
    AggregateStats,
    AlbumsStats,
    AlbumStats,
    FormatStats,
    MediaSourceStats,
    RoleBreakdown,
    SizeStats,
    StorageRole,
    YearStats,
)
from .scan import (
    DirStats,
    InodeKey,
    categorize_size_stats,
    count_live_photos,
    count_unique_pictures,
    count_unique_videos,
    scan_directory_size,
    tag_format_role,
)

__all__ = [
    "AggregateStats",
    "AlbumStats",
    "AlbumsStats",
    "FormatStats",
    "MediaSourceStats",
    "RoleBreakdown",
    "SizeStats",
    "StorageRole",
    "UnparseableAlbumNameError",
    "YearStats",
    "albums_stats_from_album_stats",
    "compute_album_stats",
    "compute_albums_stats",
    "compute_media_source_stats",
]

_ZERO = SizeStats(file_count=0, apparent_bytes=0, on_disk_bytes=0)


# ---------------------------------------------------------------------------
# Per-media-source computation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RoleStats:
    """Stats of the directories of one storage role (archive/browsable/derived)."""

    role: StorageRole
    dirs: tuple[DirStats, ...]

    @property
    def total(self) -> SizeStats:
        return merge_size_stats(d.total for d in self.dirs)

    def breakdown(self, category: Callable[[DirStats], SizeStats]) -> RoleBreakdown:
        """Merge one media category across dirs, attributed to this role."""
        s = merge_size_stats(category(d) for d in self.dirs)
        return RoleBreakdown(
            total=s,
            archive=s if self.role == StorageRole.ARCHIVE else _ZERO,
            derived=s if self.role == StorageRole.DERIVED else _ZERO,
        )

    @property
    def by_format(self) -> tuple[tuple[FormatStats, ...], ...]:
        return tuple(tag_format_role(d.by_format, role=self.role) for d in self.dirs)


def _scan_role_dirs(
    album_dir: Path,
    subdirs: list[str],
    seen_inodes: frozenset[InodeKey],
    role: StorageRole,
) -> tuple[_RoleStats, frozenset[InodeKey]]:
    """Scan the directories of one role, threading the seen-inode set through."""
    # Documented exception (docs/guidelines.md): loop-carried state — inode
    # dedup depends on every directory scanned before.
    dirs: list[DirStats] = []
    seen = seen_inodes
    for subdir in subdirs:
        dir_stats, seen = categorize_size_stats(album_dir / subdir, seen)
        dirs.append(dir_stats)
    return _RoleStats(role=role, dirs=tuple(dirs)), seen


def _scan_media_source_roles(
    album_dir: Path, ms: MediaSource, seen_inodes: frozenset[InodeKey]
) -> tuple[tuple[_RoleStats, _RoleStats, _RoleStats], frozenset[InodeKey]]:
    """Scan archive, browsable and derived dirs in that order (dedup order)."""
    archive_dirs = (
        [ms.orig_img_dir, ms.edit_img_dir, ms.orig_vid_dir, ms.edit_vid_dir]
        if (album_dir / ms.archive_dir).is_dir()
        else []
    )
    archive, seen = _scan_role_dirs(
        album_dir, archive_dirs, seen_inodes, StorageRole.ARCHIVE
    )
    browsable, seen = _scan_role_dirs(
        album_dir, [ms.img_dir, ms.vid_dir], seen, StorageRole.BROWSABLE
    )
    derived, seen = _scan_role_dirs(album_dir, [ms.jpg_dir], seen, StorageRole.DERIVED)
    return (archive, browsable, derived), seen


def compute_media_source_stats(
    album_dir: Path,
    ms: MediaSource,
    seen_inodes: frozenset[InodeKey] = frozenset(),
) -> tuple[MediaSourceStats, frozenset[InodeKey]]:
    """Compute stats for a single media source within an album.

    *seen_inodes* are inodes already counted by earlier media sources of the
    same album; the updated set is returned for the next one.
    """
    has_archive = (album_dir / ms.archive_dir).is_dir()
    roles, seen = _scan_media_source_roles(album_dir, ms, seen_inodes)
    archive, browsable, derived = roles

    def merged(category: Callable[[DirStats], SizeStats]) -> RoleBreakdown:
        return merge_role_breakdowns(r.breakdown(category) for r in roles)

    stats = MediaSourceStats(
        name=ms.name,
        media_source_type=ms.media_source_type,
        total=merge_size_stats(r.total for r in roles),
        archive=archive.total,
        original=browsable.total,
        derived=derived.total,
        unique_pictures=count_unique_pictures(album_dir, ms, has_archive=has_archive),
        unique_videos=count_unique_videos(album_dir, ms, has_archive=has_archive),
        unique_live_photos=count_live_photos(album_dir, ms, has_archive=has_archive),
        images=merged(lambda d: d.images),
        videos=merged(lambda d: d.videos),
        sidecars=merged(lambda d: d.sidecars),
        by_format=merge_format_stats(fmt for r in roles for fmt in r.by_format),
    )
    return stats, seen


# ---------------------------------------------------------------------------
# Per-album computation
# ---------------------------------------------------------------------------


class UnparseableAlbumNameError(ValueError):
    """Stats need the album year, parsed from a name that does not parse."""

    def __init__(self, album_dir: Path) -> None:
        self.album_dir = album_dir
        super().__init__(f"Album name {album_dir.name!r} cannot be parsed")


def _extract_year(album_name: str) -> str | None:
    """Extract the start year from an album directory name."""
    parsed = parse_album_name(album_name)
    return parsed.date[:4] if parsed is not None else None


def _compute_all_media_source_stats(
    album_dir: Path, media_sources: list[MediaSource]
) -> tuple[MediaSourceStats, ...]:
    # Documented exception (docs/guidelines.md): loop-carried state — the
    # seen-inode set flows from one media source to the next.
    stats: list[MediaSourceStats] = []
    seen: frozenset[InodeKey] = frozenset()
    for ms in media_sources:
        ms_stats, seen = compute_media_source_stats(album_dir, ms, seen)
        stats.append(ms_stats)
    return tuple(stats)


def compute_album_stats(album_dir: Path) -> AlbumStats:
    """Compute stats for a single album.

    Raises :class:`UnparseableAlbumNameError` when the album name cannot be
    parsed.
    """
    year = _extract_year(album_dir.name)
    if year is None:
        raise UnparseableAlbumNameError(album_dir)

    ms_stats = _compute_all_media_source_stats(
        album_dir, discover_media_sources(album_dir)
    )
    cache_size = scan_directory_size(album_dir / PHOTREE_DIR / CACHE_DIR)

    return AlbumStats(
        album_name=album_dir.name,
        album_year=year,
        by_media_source=ms_stats,
        aggregate=aggregate_media_sources(ms_stats),
        cache_storage=cache_size if cache_size.file_count > 0 else None,
    )


# ---------------------------------------------------------------------------
# Gallery computation
# ---------------------------------------------------------------------------


def albums_stats_from_album_stats(
    album_stats_list: list[AlbumStats],
) -> AlbumsStats:
    """Build ``AlbumsStats`` from pre-computed per-album stats."""
    all_ms_names = sorted(
        {ms.name for a in album_stats_list for ms in a.by_media_source}
    )

    sorted_albums = sorted(album_stats_list, key=lambda a: a.album_year)
    by_year = tuple(
        YearStats(
            year=year,
            album_count=len(group := list(albums)),
            aggregate=merge_aggregates(a.aggregate for a in group),
            cache_storage=_merged_cache(group),
        )
        for year, albums in groupby(sorted_albums, key=lambda a: a.album_year)
    )

    return AlbumsStats(
        album_count=len(album_stats_list),
        by_album=tuple(album_stats_list),
        aggregate=merge_aggregates(a.aggregate for a in album_stats_list),
        unique_media_source_names=tuple(all_ms_names),
        by_year=by_year,
        cache_storage=_merged_cache(album_stats_list),
    )


def _merged_cache(albums: list[AlbumStats]) -> SizeStats | None:
    """Sum the albums' cache storage; ``None`` when none of them has a cache."""
    caches = [a.cache_storage for a in albums if a.cache_storage]
    return merge_size_stats(caches) if caches else None


def compute_albums_stats(
    albums: list[Path],
    *,
    on_album_done: Callable[[str], None] | None = None,
) -> AlbumsStats:
    """Compute aggregated stats for a set of albums.

    Raises :class:`ValueError` when any album name cannot be parsed.
    """
    album_stats_list = [
        _compute_and_notify(album_dir, on_album_done) for album_dir in albums
    ]
    return albums_stats_from_album_stats(album_stats_list)


def _compute_and_notify(
    album_dir: Path,
    on_album_done: Callable[[str], None] | None,
) -> AlbumStats:
    stats = compute_album_stats(album_dir)
    if on_album_done is not None:
        on_album_done(album_dir.name)
    return stats
