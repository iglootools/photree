"""Album and gallery statistics computation.

Computes disk usage, file counts, and content breakdowns for albums and
galleries. All results are frozen dataclasses suitable for display via
the output formatting layer.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import groupby
from pathlib import Path

from ..naming import parse_album_name
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import MediaSource
from .aggregate import (
    aggregate_media_sources,
    merge_aggregates,
    merge_format_stats,
    merge_size_stats,
)
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
    scan_directory_size,
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

_ZERO = SizeStats(file_count=0, apparent_bytes=0, on_disk_bytes=0)
_ZERO_ROLE = RoleBreakdown(total=_ZERO, archive=_ZERO, derived=_ZERO)


# ---------------------------------------------------------------------------
# Per-media-source computation
# ---------------------------------------------------------------------------


def _scan_role_dirs(
    album_dir: Path,
    subdirs: list[str],
    seen_inodes: set[tuple[int, int]],
    role: str,
) -> tuple[
    SizeStats,
    RoleBreakdown,
    RoleBreakdown,
    RoleBreakdown,
    list[tuple[FormatStats, ...]],
]:
    """Scan directories for a single role (archive, browsable, derived).

    Returns ``(total, images_role, videos_role, sidecars_role, format_groups)``.
    """
    parts: list[SizeStats] = []
    img_parts: list[SizeStats] = []
    vid_parts: list[SizeStats] = []
    sc_parts: list[SizeStats] = []
    fmt_groups: list[tuple[FormatStats, ...]] = []

    for subdir in subdirs:
        imgs, vids, scs, fmts = categorize_size_stats(album_dir / subdir, seen_inodes)
        parts.append(merge_size_stats([imgs, vids, scs]))
        img_parts.append(imgs)
        vid_parts.append(vids)
        sc_parts.append(scs)
        fmt_groups.append(tag_format_role(fmts, role=role))

    total = merge_size_stats(parts)
    img_total = merge_size_stats(img_parts)
    vid_total = merge_size_stats(vid_parts)
    sc_total = merge_size_stats(sc_parts)

    def _role_breakdown(s: SizeStats) -> RoleBreakdown:
        match role:
            case "archive":
                return RoleBreakdown(total=s, archive=s, derived=_ZERO)
            case "derived":
                return RoleBreakdown(total=s, archive=_ZERO, derived=s)
            case _:
                return RoleBreakdown(total=s, archive=_ZERO, derived=_ZERO)

    return (
        total,
        _role_breakdown(img_total),
        _role_breakdown(vid_total),
        _role_breakdown(sc_total),
        fmt_groups,
    )


def compute_media_source_stats(
    album_dir: Path,
    ms: MediaSource,
    seen_inodes: set[tuple[int, int]],
) -> MediaSourceStats:
    """Compute stats for a single media source within an album."""
    has_archive = (album_dir / ms.archive_dir).is_dir()

    # Archive directories
    if has_archive:
        archive_total, arch_img, arch_vid, arch_sc, arch_fmts = _scan_role_dirs(
            album_dir,
            [ms.orig_img_dir, ms.edit_img_dir, ms.orig_vid_dir, ms.edit_vid_dir],
            seen_inodes,
            "archive",
        )
    else:
        archive_total = _ZERO
        arch_img = arch_vid = arch_sc = _ZERO_ROLE
        arch_fmts = []

    # Browsable directories ({name}-img/, {name}-vid/)
    browsable_total, browse_img, browse_vid, browse_sc, browse_fmts = _scan_role_dirs(
        album_dir, [ms.img_dir, ms.vid_dir], seen_inodes, "browsable"
    )

    # Derived directory ({name}-jpg/)
    derived_total, der_img, der_vid, der_sc, der_fmts = _scan_role_dirs(
        album_dir, [ms.jpg_dir], seen_inodes, "derived"
    )

    from .aggregate import merge_role_breakdowns

    return MediaSourceStats(
        name=ms.name,
        media_source_type=ms.media_source_type,
        total=merge_size_stats([archive_total, browsable_total, derived_total]),
        archive=archive_total,
        original=browsable_total,
        derived=derived_total,
        unique_pictures=count_unique_pictures(album_dir, ms, has_archive=has_archive),
        unique_videos=count_unique_videos(album_dir, ms, has_archive=has_archive),
        images=merge_role_breakdowns([arch_img, browse_img, der_img]),
        videos=merge_role_breakdowns([arch_vid, browse_vid, der_vid]),
        sidecars=merge_role_breakdowns([arch_sc, browse_sc, der_sc]),
        by_format=merge_format_stats([*arch_fmts, *browse_fmts, *der_fmts]),
    )


# ---------------------------------------------------------------------------
# Per-album computation
# ---------------------------------------------------------------------------


def _extract_year(album_name: str) -> str | None:
    """Extract the start year from an album directory name."""
    parsed = parse_album_name(album_name)
    return parsed.date[:4] if parsed is not None else None


def compute_album_stats(album_dir: Path) -> AlbumStats:
    """Compute stats for a single album.

    Raises :class:`ValueError` when the album name cannot be parsed.
    """
    from ..faces.store import faces_dir

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

    face_storage = scan_directory_size(faces_dir(album_dir))

    return AlbumStats(
        album_name=album_name,
        album_year=year,
        by_media_source=ms_stats,
        aggregate=aggregate_media_sources(ms_stats),
        face_storage=face_storage if face_storage.file_count > 0 else None,
    )


# ---------------------------------------------------------------------------
# Gallery computation
# ---------------------------------------------------------------------------


def gallery_stats_from_album_stats(
    album_stats_list: list[AlbumStats],
) -> GalleryStats:
    """Build ``GalleryStats`` from pre-computed per-album stats."""
    all_ms_names = sorted(
        {ms.name for a in album_stats_list for ms in a.by_media_source}
    )

    sorted_albums = sorted(album_stats_list, key=lambda a: a.album_year)
    by_year = tuple(
        YearStats(
            year=year,
            album_count=len(group := list(albums)),
            aggregate=merge_aggregates(a.aggregate for a in group),
        )
        for year, albums in groupby(sorted_albums, key=lambda a: a.album_year)
    )

    album_face_sizes = [a.face_storage for a in album_stats_list if a.face_storage]
    face_storage = merge_size_stats(album_face_sizes) if album_face_sizes else None

    return GalleryStats(
        album_count=len(album_stats_list),
        by_album=tuple(album_stats_list),
        aggregate=merge_aggregates(a.aggregate for a in album_stats_list),
        unique_media_source_names=tuple(all_ms_names),
        by_year=by_year,
        face_storage=face_storage,
    )


def compute_gallery_stats(
    albums: list[Path],
    *,
    on_album_done: Callable[[str], None] | None = None,
) -> GalleryStats:
    """Compute aggregated stats for a set of albums.

    Raises :class:`ValueError` when any album name cannot be parsed.
    """
    album_stats_list = [
        _compute_and_notify(album_dir, on_album_done) for album_dir in albums
    ]
    return gallery_stats_from_album_stats(album_stats_list)


def _compute_and_notify(
    album_dir: Path,
    on_album_done: Callable[[str], None] | None,
) -> AlbumStats:
    stats = compute_album_stats(album_dir)
    if on_album_done is not None:
        on_album_done(album_dir.name)
    return stats
