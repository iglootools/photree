"""Fake stats data for demo and testing purposes."""

from __future__ import annotations

from ..store.protocol import MediaSourceType
from .models import (
    AggregateStats,
    AlbumStats,
    FormatStats,
    GalleryStats,
    MediaSourceStats,
    RoleBreakdown,
    SizeStats,
    YearStats,
)


def _gb(n: float) -> int:
    return int(n * 1024 * 1024 * 1024)


def _mb(n: float) -> int:
    return int(n * 1024 * 1024)


def _rb(
    total: SizeStats,
    archive: SizeStats = SizeStats(0, 0, 0),
    derived: SizeStats = SizeStats(0, 0, 0),
) -> RoleBreakdown:
    return RoleBreakdown(total=total, archive=archive, derived=derived)


# ---------------------------------------------------------------------------
# Media source stats
# ---------------------------------------------------------------------------

_IOS_MAIN = MediaSourceStats(
    name="main",
    media_source_type=MediaSourceType.IOS,
    total=SizeStats(file_count=1842, apparent_bytes=_gb(48.3), on_disk_bytes=_gb(32.1)),
    archive=SizeStats(
        file_count=980, apparent_bytes=_gb(28.5), on_disk_bytes=_gb(28.5)
    ),
    original=SizeStats(file_count=490, apparent_bytes=_gb(16.2), on_disk_bytes=0),
    derived=SizeStats(file_count=372, apparent_bytes=_gb(3.6), on_disk_bytes=_gb(3.6)),
    unique_pictures=372,
    unique_videos=28,
    images=_rb(
        total=SizeStats(
            file_count=1234, apparent_bytes=_gb(22.4), on_disk_bytes=_gb(14.8)
        ),
        archive=SizeStats(
            file_count=620, apparent_bytes=_gb(17.0), on_disk_bytes=_gb(17.0)
        ),
        derived=SizeStats(
            file_count=372, apparent_bytes=_gb(3.6), on_disk_bytes=_gb(3.6)
        ),
    ),
    videos=_rb(
        total=SizeStats(
            file_count=84, apparent_bytes=_gb(24.1), on_disk_bytes=_gb(16.0)
        ),
        archive=SizeStats(
            file_count=56, apparent_bytes=_gb(10.8), on_disk_bytes=_gb(10.8)
        ),
    ),
    sidecars=_rb(
        total=SizeStats(
            file_count=524, apparent_bytes=_mb(42.5), on_disk_bytes=_mb(42.5)
        ),
        archive=SizeStats(
            file_count=524, apparent_bytes=_mb(42.5), on_disk_bytes=_mb(42.5)
        ),
    ),
    by_format=(
        FormatStats(".mov", 84, _gb(24.1), 0, _gb(10.8), 0),
        FormatStats(".heic", 744, _gb(18.6), 0, _gb(14.0), 0),
        FormatStats(".jpg", 372, _gb(3.6), 0, 0, _gb(3.6)),
        FormatStats(".dng", 34, _gb(2.0), 0, _gb(2.0), 0),
        FormatStats(".aae", 524, _mb(42.5), 0, _mb(42.5), 0),
        FormatStats(".png", 84, _mb(180), 0, _mb(100), _mb(80)),
    ),
)

_PLAIN_NELU = MediaSourceStats(
    name="nelu",
    media_source_type=MediaSourceType.STD,
    total=SizeStats(file_count=186, apparent_bytes=_gb(6.2), on_disk_bytes=_gb(6.2)),
    archive=SizeStats(file_count=0, apparent_bytes=0, on_disk_bytes=0),
    original=SizeStats(file_count=124, apparent_bytes=_gb(5.1), on_disk_bytes=_gb(5.1)),
    derived=SizeStats(file_count=62, apparent_bytes=_gb(1.1), on_disk_bytes=_gb(1.1)),
    unique_pictures=62,
    unique_videos=0,
    images=_rb(
        total=SizeStats(
            file_count=186, apparent_bytes=_gb(6.2), on_disk_bytes=_gb(6.2)
        ),
        derived=SizeStats(
            file_count=62, apparent_bytes=_gb(1.1), on_disk_bytes=_gb(1.1)
        ),
    ),
    videos=_rb(total=SizeStats(0, 0, 0)),
    sidecars=_rb(total=SizeStats(0, 0, 0)),
    by_format=(
        FormatStats(".heic", 62, _gb(3.2), 0, 0, 0),
        FormatStats(".jpg", 124, _gb(3.0), 0, 0, _gb(1.1)),
    ),
)


# ---------------------------------------------------------------------------
# Album stats
# ---------------------------------------------------------------------------

_AGGREGATE_ALBUM = AggregateStats(
    total=SizeStats(file_count=2028, apparent_bytes=_gb(54.5), on_disk_bytes=_gb(38.3)),
    archive=SizeStats(
        file_count=980, apparent_bytes=_gb(28.5), on_disk_bytes=_gb(28.5)
    ),
    original=SizeStats(
        file_count=614, apparent_bytes=_gb(21.3), on_disk_bytes=_gb(5.1)
    ),
    derived=SizeStats(file_count=434, apparent_bytes=_gb(4.7), on_disk_bytes=_gb(4.7)),
    unique_pictures=434,
    unique_videos=28,
    images=_rb(
        total=SizeStats(
            file_count=1420, apparent_bytes=_gb(28.6), on_disk_bytes=_gb(21.0)
        ),
        archive=SizeStats(
            file_count=620, apparent_bytes=_gb(17.0), on_disk_bytes=_gb(17.0)
        ),
        derived=SizeStats(
            file_count=434, apparent_bytes=_gb(4.7), on_disk_bytes=_gb(4.7)
        ),
    ),
    videos=_rb(
        total=SizeStats(
            file_count=84, apparent_bytes=_gb(24.1), on_disk_bytes=_gb(16.0)
        ),
        archive=SizeStats(
            file_count=56, apparent_bytes=_gb(10.8), on_disk_bytes=_gb(10.8)
        ),
    ),
    sidecars=_rb(
        total=SizeStats(
            file_count=524, apparent_bytes=_mb(42.5), on_disk_bytes=_mb(42.5)
        ),
        archive=SizeStats(
            file_count=524, apparent_bytes=_mb(42.5), on_disk_bytes=_mb(42.5)
        ),
    ),
    by_format=(
        FormatStats(".mov", 84, _gb(24.1), 0, _gb(10.8), 0),
        FormatStats(".heic", 806, _gb(21.8), 0, _gb(14.0), 0),
        FormatStats(".jpg", 496, _gb(6.6), 0, 0, _gb(4.7)),
        FormatStats(".dng", 34, _gb(2.0), 0, _gb(2.0), 0),
        FormatStats(".png", 84, _mb(180), 0, _mb(100), _mb(80)),
        FormatStats(".aae", 524, _mb(42.5), 0, _mb(42.5), 0),
    ),
    media_source_count=2,
    by_media_source_type=(
        (MediaSourceType.IOS, 1),
        (MediaSourceType.STD, 1),
    ),
)

ALBUM_STATS = AlbumStats(
    album_name="2024-07-14 - 01 - Canada Trip - Hiking the Rockies @ Banff NP, AB, CA",
    album_year="2024",
    by_media_source=(_IOS_MAIN, _PLAIN_NELU),
    aggregate=_AGGREGATE_ALBUM,
)


# ---------------------------------------------------------------------------
# Gallery stats (3 albums across 2 years)
# ---------------------------------------------------------------------------

_ALBUM_2024_A = AlbumStats(
    album_name="2024-07-14 - 01 - Canada Trip - Hiking the Rockies",
    album_year="2024",
    by_media_source=(_IOS_MAIN,),
    aggregate=AggregateStats(
        total=SizeStats(
            file_count=1842, apparent_bytes=_gb(48.3), on_disk_bytes=_gb(32.1)
        ),
        archive=SizeStats(
            file_count=980, apparent_bytes=_gb(28.5), on_disk_bytes=_gb(28.5)
        ),
        original=SizeStats(file_count=490, apparent_bytes=_gb(16.2), on_disk_bytes=0),
        derived=SizeStats(
            file_count=372, apparent_bytes=_gb(3.6), on_disk_bytes=_gb(3.6)
        ),
        unique_pictures=372,
        unique_videos=28,
        images=_IOS_MAIN.images,
        videos=_IOS_MAIN.videos,
        sidecars=_IOS_MAIN.sidecars,
        by_format=_IOS_MAIN.by_format,
        media_source_count=1,
        by_media_source_type=((MediaSourceType.IOS, 1),),
    ),
)

_ALBUM_2024_B = AlbumStats(
    album_name="2024-08-01 - Lake Louise Kayaking",
    album_year="2024",
    by_media_source=(_IOS_MAIN, _PLAIN_NELU),
    aggregate=_AGGREGATE_ALBUM,
)

_ALBUM_2025 = AlbumStats(
    album_name="2025-01-10 - Winter in Montreal",
    album_year="2025",
    by_media_source=(_IOS_MAIN,),
    aggregate=AggregateStats(
        total=SizeStats(
            file_count=620, apparent_bytes=_gb(15.8), on_disk_bytes=_gb(10.5)
        ),
        archive=SizeStats(
            file_count=310, apparent_bytes=_gb(9.2), on_disk_bytes=_gb(9.2)
        ),
        original=SizeStats(file_count=155, apparent_bytes=_gb(5.3), on_disk_bytes=0),
        derived=SizeStats(
            file_count=155, apparent_bytes=_gb(1.3), on_disk_bytes=_gb(1.3)
        ),
        unique_pictures=145,
        unique_videos=10,
        images=_rb(
            total=SizeStats(
                file_count=455, apparent_bytes=_gb(8.5), on_disk_bytes=_gb(5.6)
            ),
            archive=SizeStats(
                file_count=230, apparent_bytes=_gb(5.8), on_disk_bytes=_gb(5.8)
            ),
            derived=SizeStats(
                file_count=155, apparent_bytes=_gb(1.3), on_disk_bytes=_gb(1.3)
            ),
        ),
        videos=_rb(
            total=SizeStats(
                file_count=30, apparent_bytes=_gb(6.8), on_disk_bytes=_gb(4.5)
            ),
            archive=SizeStats(
                file_count=20, apparent_bytes=_gb(3.2), on_disk_bytes=_gb(3.2)
            ),
        ),
        sidecars=_rb(
            total=SizeStats(
                file_count=135, apparent_bytes=_mb(11.2), on_disk_bytes=_mb(11.2)
            ),
            archive=SizeStats(
                file_count=135, apparent_bytes=_mb(11.2), on_disk_bytes=_mb(11.2)
            ),
        ),
        by_format=(
            FormatStats(".mov", 30, _gb(6.8), 0, _gb(3.2), 0),
            FormatStats(".heic", 300, _gb(7.5), 0, _gb(5.5), 0),
            FormatStats(".jpg", 155, _gb(1.3), 0, 0, _gb(1.3)),
            FormatStats(".aae", 135, _mb(11.2), 0, _mb(11.2), 0),
        ),
        media_source_count=1,
        by_media_source_type=((MediaSourceType.IOS, 1),),
    ),
)

_GALLERY_AGGREGATE = AggregateStats(
    total=SizeStats(
        file_count=4490, apparent_bytes=_gb(118.6), on_disk_bytes=_gb(80.9)
    ),
    archive=SizeStats(
        file_count=2270, apparent_bytes=_gb(66.2), on_disk_bytes=_gb(66.2)
    ),
    original=SizeStats(
        file_count=1259, apparent_bytes=_gb(42.8), on_disk_bytes=_gb(5.1)
    ),
    derived=SizeStats(file_count=961, apparent_bytes=_gb(9.6), on_disk_bytes=_gb(9.6)),
    unique_pictures=951,
    unique_videos=66,
    images=_rb(
        total=SizeStats(
            file_count=3109, apparent_bytes=_gb(59.5), on_disk_bytes=_gb(41.4)
        ),
        archive=SizeStats(
            file_count=1470, apparent_bytes=_gb(39.8), on_disk_bytes=_gb(39.8)
        ),
        derived=SizeStats(
            file_count=961, apparent_bytes=_gb(9.6), on_disk_bytes=_gb(9.6)
        ),
    ),
    videos=_rb(
        total=SizeStats(
            file_count=198, apparent_bytes=_gb(55.0), on_disk_bytes=_gb(36.5)
        ),
        archive=SizeStats(
            file_count=132, apparent_bytes=_gb(24.8), on_disk_bytes=_gb(24.8)
        ),
    ),
    sidecars=_rb(
        total=SizeStats(
            file_count=1183, apparent_bytes=_mb(96.2), on_disk_bytes=_mb(96.2)
        ),
        archive=SizeStats(
            file_count=1183, apparent_bytes=_mb(96.2), on_disk_bytes=_mb(96.2)
        ),
    ),
    by_format=(
        FormatStats(".mov", 198, _gb(55.0), 0, _gb(24.8), 0),
        FormatStats(".heic", 1788, _gb(44.7), 0, _gb(33.5), 0),
        FormatStats(".jpg", 1023, _gb(11.5), 0, 0, _gb(9.6)),
        FormatStats(".dng", 68, _gb(4.0), 0, _gb(4.0), 0),
        FormatStats(".png", 168, _mb(360), 0, _mb(200), _mb(160)),
        FormatStats(".aae", 1183, _mb(96.2), 0, _mb(96.2), 0),
    ),
    media_source_count=4,
    by_media_source_type=(
        (MediaSourceType.IOS, 3),
        (MediaSourceType.STD, 1),
    ),
)

GALLERY_STATS = GalleryStats(
    album_count=3,
    by_album=(_ALBUM_2024_A, _ALBUM_2024_B, _ALBUM_2025),
    aggregate=_GALLERY_AGGREGATE,
    unique_media_source_names=("main", "nelu"),
    by_year=(
        YearStats(
            year="2024",
            album_count=2,
            aggregate=AggregateStats(
                total=SizeStats(
                    file_count=3870,
                    apparent_bytes=_gb(102.8),
                    on_disk_bytes=_gb(70.4),
                ),
                archive=SizeStats(
                    file_count=1960, apparent_bytes=_gb(57.0), on_disk_bytes=_gb(57.0)
                ),
                original=SizeStats(
                    file_count=1104, apparent_bytes=_gb(37.5), on_disk_bytes=_gb(5.1)
                ),
                derived=SizeStats(
                    file_count=806, apparent_bytes=_gb(8.3), on_disk_bytes=_gb(8.3)
                ),
                unique_pictures=806,
                unique_videos=56,
                images=_rb(
                    total=SizeStats(
                        file_count=2654,
                        apparent_bytes=_gb(51.0),
                        on_disk_bytes=_gb(35.8),
                    ),
                    archive=SizeStats(
                        file_count=1240,
                        apparent_bytes=_gb(34.0),
                        on_disk_bytes=_gb(34.0),
                    ),
                    derived=SizeStats(
                        file_count=806, apparent_bytes=_gb(8.3), on_disk_bytes=_gb(8.3)
                    ),
                ),
                videos=_rb(
                    total=SizeStats(
                        file_count=168,
                        apparent_bytes=_gb(48.2),
                        on_disk_bytes=_gb(32.0),
                    ),
                    archive=SizeStats(
                        file_count=112,
                        apparent_bytes=_gb(21.6),
                        on_disk_bytes=_gb(21.6),
                    ),
                ),
                sidecars=_rb(
                    total=SizeStats(
                        file_count=1048,
                        apparent_bytes=_mb(85.0),
                        on_disk_bytes=_mb(85.0),
                    ),
                    archive=SizeStats(
                        file_count=1048,
                        apparent_bytes=_mb(85.0),
                        on_disk_bytes=_mb(85.0),
                    ),
                ),
                by_format=(
                    FormatStats(".mov", 168, _gb(48.2), 0, _gb(21.6), 0),
                    FormatStats(".heic", 1488, _gb(37.2), 0, _gb(28.0), 0),
                    FormatStats(".jpg", 868, _gb(10.2), 0, 0, _gb(8.3)),
                    FormatStats(".dng", 68, _gb(4.0), 0, _gb(4.0), 0),
                    FormatStats(".png", 168, _mb(360), 0, _mb(200), _mb(160)),
                    FormatStats(".aae", 1048, _mb(85.0), 0, _mb(85.0), 0),
                ),
                media_source_count=3,
                by_media_source_type=(
                    (MediaSourceType.IOS, 2),
                    (MediaSourceType.STD, 1),
                ),
            ),
        ),
        YearStats(
            year="2025",
            album_count=1,
            aggregate=_ALBUM_2025.aggregate,
        ),
    ),
)
