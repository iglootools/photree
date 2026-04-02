"""Tests for photree.album.stats module."""

import os
from pathlib import Path

import pytest

from photree.album.stats import (
    AlbumStats,
    FormatStats,
    SizeStats,
    _categorize_size_stats,
    _count_unique_pictures,
    _count_unique_videos,
    _extract_year,
    _merge_format_stats,
    _merge_size_stats,
    _scan_directory,
    compute_album_stats,
    compute_media_source_stats,
    gallery_stats_from_album_stats,
)
from photree.album.store.fs import save_album_metadata
from photree.album.store.protocol import (
    AlbumMetadata,
    MAIN_MEDIA_SOURCE,
    MediaSourceType,
    generate_album_id,
    std_media_source,
)
from photree.fsprotocol import PHOTREE_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_album(album: Path) -> None:
    """Create the .photree marker and album.yaml for album detection."""
    (album / PHOTREE_DIR).mkdir(parents=True, exist_ok=True)
    save_album_metadata(album, AlbumMetadata(id=generate_album_id()))


def _setup_ios_album(album: Path) -> None:
    """Create a well-formed iOS album with a .photree marker."""
    _make_album(album)

    ms = MAIN_MEDIA_SOURCE
    _write(album / ms.orig_img_dir / "IMG_0001.HEIC", "a" * 100)
    _write(album / ms.orig_img_dir / "IMG_0001.AAE", "b" * 20)
    _write(album / ms.orig_img_dir / "IMG_0002.PNG", "c" * 80)

    _write(album / ms.edit_img_dir / "IMG_E0001.HEIC", "d" * 110)
    _write(album / ms.edit_img_dir / "IMG_O0001.AAE", "e" * 25)

    # main-img: hardlinks to archive originals/edits
    (album / ms.img_dir).mkdir(parents=True, exist_ok=True)
    os.link(
        album / ms.edit_img_dir / "IMG_E0001.HEIC",
        album / ms.img_dir / "IMG_E0001.HEIC",
    )
    os.link(
        album / ms.orig_img_dir / "IMG_0002.PNG",
        album / ms.img_dir / "IMG_0002.PNG",
    )

    _write(album / ms.orig_vid_dir / "IMG_0003.MOV", "f" * 500)
    (album / ms.edit_vid_dir).mkdir(parents=True, exist_ok=True)
    (album / ms.vid_dir).mkdir(parents=True, exist_ok=True)
    os.link(
        album / ms.orig_vid_dir / "IMG_0003.MOV",
        album / ms.vid_dir / "IMG_0003.MOV",
    )

    _write(album / ms.jpg_dir / "IMG_E0001.jpg", "g" * 60)
    _write(album / ms.jpg_dir / "IMG_0002.PNG", "c" * 80)


# ---------------------------------------------------------------------------
# _scan_directory
# ---------------------------------------------------------------------------


class TestScanDirectory:
    def test_empty_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        seen: set[tuple[int, int]] = set()
        size, by_fmt = _scan_directory(d, seen)
        assert size == SizeStats(0, 0, 0)
        assert by_fmt == ()
        assert seen == set()

    def test_missing_directory(self, tmp_path: Path) -> None:
        seen: set[tuple[int, int]] = set()
        size, by_fmt = _scan_directory(tmp_path / "nonexistent", seen)
        assert size == SizeStats(0, 0, 0)

    def test_files_counted(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.heic", "x" * 50)
        _write(tmp_path / "b.mov", "y" * 100)
        seen: set[tuple[int, int]] = set()
        size, by_fmt = _scan_directory(tmp_path, seen)
        assert size.file_count == 2
        assert size.apparent_bytes == 150
        assert size.on_disk_bytes == 150
        assert len(seen) == 2

    def test_hardlink_dedup(self, tmp_path: Path) -> None:
        _write(tmp_path / "orig" / "a.heic", "x" * 50)
        (tmp_path / "link").mkdir()
        os.link(tmp_path / "orig" / "a.heic", tmp_path / "link" / "a.heic")

        seen: set[tuple[int, int]] = set()
        s1, _ = _scan_directory(tmp_path / "orig", seen)
        assert s1.on_disk_bytes == 50

        s2, _ = _scan_directory(tmp_path / "link", seen)
        assert s2.apparent_bytes == 50
        assert s2.on_disk_bytes == 0  # already seen

    def test_symlink_dedup(self, tmp_path: Path) -> None:
        _write(tmp_path / "orig" / "a.heic", "x" * 50)
        (tmp_path / "link").mkdir()
        rel = os.path.relpath(tmp_path / "orig" / "a.heic", tmp_path / "link")
        os.symlink(rel, tmp_path / "link" / "a.heic")

        seen: set[tuple[int, int]] = set()
        s1, _ = _scan_directory(tmp_path / "orig", seen)
        s2, _ = _scan_directory(tmp_path / "link", seen)
        assert s2.on_disk_bytes == 0

    def test_format_breakdown(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.heic", "x" * 50)
        _write(tmp_path / "b.heic", "y" * 30)
        _write(tmp_path / "c.mov", "z" * 100)
        seen: set[tuple[int, int]] = set()
        _, by_fmt = _scan_directory(tmp_path, seen)
        fmt_dict = {fs.extension: fs for fs in by_fmt}
        assert fmt_dict[".mov"].apparent_bytes == 100
        assert fmt_dict[".heic"].apparent_bytes == 80
        assert fmt_dict[".heic"].file_count == 2


# ---------------------------------------------------------------------------
# _categorize_size_stats
# ---------------------------------------------------------------------------


class TestCategorizeSizeStats:
    def test_categorizes_by_type(self, tmp_path: Path) -> None:
        _write(tmp_path / "a.heic", "x" * 50)
        _write(tmp_path / "b.mov", "y" * 100)
        _write(tmp_path / "c.aae", "z" * 10)
        seen: set[tuple[int, int]] = set()
        imgs, vids, scs, _ = _categorize_size_stats(tmp_path, seen)
        assert imgs.file_count == 1
        assert imgs.apparent_bytes == 50
        assert vids.file_count == 1
        assert vids.apparent_bytes == 100
        assert scs.file_count == 1
        assert scs.apparent_bytes == 10


# ---------------------------------------------------------------------------
# Unique media counting
# ---------------------------------------------------------------------------


class TestUniqueMediaCounting:
    def test_unique_pictures_ios_with_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        ms = MAIN_MEDIA_SOURCE
        _write(album / ms.orig_img_dir / "IMG_0001.HEIC")
        _write(album / ms.orig_img_dir / "IMG_0002.HEIC")
        _write(album / ms.orig_img_dir / "IMG_0002.AAE")  # sidecar, not a picture
        assert _count_unique_pictures(album, ms, has_archive=True) == 2

    def test_unique_pictures_std_without_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        ms = std_media_source("nelu")
        _write(album / ms.img_dir / "photo1.heic")
        _write(album / ms.img_dir / "photo2.jpg")
        _write(album / ms.img_dir / "photo2.aae")  # not IMG_EXTENSIONS
        assert _count_unique_pictures(album, ms, has_archive=False) == 2

    def test_unique_pictures_std_with_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        ms = std_media_source("nelu")
        _write(album / ms.orig_img_dir / "photo1.heic")
        _write(album / ms.orig_img_dir / "photo2.jpg")
        _write(album / ms.orig_img_dir / "photo2.aae")  # not IMG_EXTENSIONS
        assert _count_unique_pictures(album, ms, has_archive=True) == 2

    def test_unique_videos_ios_with_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        ms = MAIN_MEDIA_SOURCE
        _write(album / ms.orig_vid_dir / "IMG_0001.MOV")
        _write(album / ms.orig_vid_dir / "IMG_0002.MOV")
        assert _count_unique_videos(album, ms, has_archive=True) == 2

    def test_unique_videos_std_without_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        ms = std_media_source("nelu")
        _write(album / ms.vid_dir / "clip1.mov")
        assert _count_unique_videos(album, ms, has_archive=False) == 1

    def test_unique_videos_std_with_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        ms = std_media_source("nelu")
        _write(album / ms.orig_vid_dir / "clip1.mov")
        _write(album / ms.orig_vid_dir / "clip2.mov")
        assert _count_unique_videos(album, ms, has_archive=True) == 2


# ---------------------------------------------------------------------------
# Year extraction
# ---------------------------------------------------------------------------


class TestExtractYear:
    def test_full_date(self) -> None:
        assert _extract_year("2024-07-14 - Title") == "2024"

    def test_month_precision(self) -> None:
        assert _extract_year("2024-07 - Title") == "2024"

    def test_year_precision(self) -> None:
        assert _extract_year("2024 - Title") == "2024"

    def test_date_range(self) -> None:
        assert _extract_year("2024-07-14--2025-01-01 - Title") == "2024"

    def test_unparseable(self) -> None:
        assert _extract_year("not a valid name") is None


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


class TestMergeSizeStats:
    def test_sums_fields(self) -> None:
        a = SizeStats(file_count=2, apparent_bytes=100, on_disk_bytes=80)
        b = SizeStats(file_count=3, apparent_bytes=200, on_disk_bytes=150)
        result = _merge_size_stats([a, b])
        assert result == SizeStats(file_count=5, apparent_bytes=300, on_disk_bytes=230)

    def test_empty(self) -> None:
        result = _merge_size_stats([])
        assert result == SizeStats(0, 0, 0)


class TestMergeFormatStats:
    def test_groups_by_extension(self) -> None:
        g1 = (FormatStats(".heic", 2, 100, 0, 0, 0),)
        g2 = (
            FormatStats(".heic", 3, 150, 0, 0, 0),
            FormatStats(".mov", 1, 200, 0, 0, 0),
        )
        result = _merge_format_stats([g1, g2])
        fmt_dict = {fs.extension: fs for fs in result}
        assert fmt_dict[".heic"].file_count == 5
        assert fmt_dict[".heic"].apparent_bytes == 250
        assert fmt_dict[".mov"].file_count == 1

    def test_sorted_by_bytes_desc(self) -> None:
        g = (
            FormatStats(".aae", 10, 50, 0, 0, 0),
            FormatStats(".heic", 2, 500, 0, 0, 0),
        )
        result = _merge_format_stats([g])
        assert result[0].extension == ".heic"
        assert result[1].extension == ".aae"


# ---------------------------------------------------------------------------
# compute_media_source_stats
# ---------------------------------------------------------------------------


class TestComputeMediaSourceStats:
    def test_ios_source(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Test"
        _setup_ios_album(album)
        ms = MAIN_MEDIA_SOURCE
        seen: set[tuple[int, int]] = set()
        result = compute_media_source_stats(album, ms, seen)

        assert result.name == "main"
        assert result.media_source_type == MediaSourceType.IOS
        assert result.unique_pictures == 2  # IMG_0001, IMG_0002
        assert result.unique_videos == 1  # IMG_0003

        # Archive: orig-img (3 files) + edit-img (2 files) + orig-vid (1) + edit-vid (0)
        assert result.archive.file_count == 6
        # Derived: jpg dir (2 files)
        assert result.derived.file_count == 2
        # Original/browsable: img (2) + vid (1)
        assert result.original.file_count == 3

        # On-disk should be less than apparent due to hardlinks
        assert result.total.on_disk_bytes < result.total.apparent_bytes

        # RoleBreakdown: images in archive should include HEIC+PNG from orig/edit
        assert result.images.archive.file_count > 0
        # Derived images should be the jpg dir contents
        assert result.images.derived.file_count == 2  # IMG_E0001.jpg + IMG_0002.PNG

    def test_std_source_without_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Test"
        _make_album(album)
        ms = std_media_source("nelu")
        _write(album / ms.img_dir / "photo1.heic", "x" * 100)
        _write(album / ms.img_dir / "photo2.jpg", "y" * 80)
        _write(album / ms.vid_dir / "clip1.mov", "z" * 500)
        _write(album / ms.jpg_dir / "photo1.jpg", "w" * 60)
        _write(album / ms.jpg_dir / "photo2.jpg", "y" * 80)

        seen: set[tuple[int, int]] = set()
        result = compute_media_source_stats(album, ms, seen)

        assert result.media_source_type == MediaSourceType.STD
        assert result.unique_pictures == 2
        assert result.unique_videos == 1
        assert result.archive == SizeStats(0, 0, 0)  # no archive dir on disk
        assert result.original.file_count == 3  # img(2) + vid(1)
        assert result.derived.file_count == 2  # jpg(2)

    def test_std_source_with_archive(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Test"
        _make_album(album)
        ms = std_media_source("nelu")

        # Archive directories (std-nelu/)
        _write(album / ms.orig_img_dir / "photo1.heic", "a" * 100)
        _write(album / ms.orig_img_dir / "photo2.jpg", "b" * 80)
        (album / ms.edit_img_dir).mkdir(parents=True, exist_ok=True)
        _write(album / ms.orig_vid_dir / "clip1.mov", "c" * 500)
        (album / ms.edit_vid_dir).mkdir(parents=True, exist_ok=True)

        # Browsable directories (hardlinks to archive)
        (album / ms.img_dir).mkdir(parents=True, exist_ok=True)
        os.link(
            album / ms.orig_img_dir / "photo1.heic",
            album / ms.img_dir / "photo1.heic",
        )
        os.link(
            album / ms.orig_img_dir / "photo2.jpg",
            album / ms.img_dir / "photo2.jpg",
        )
        (album / ms.vid_dir).mkdir(parents=True, exist_ok=True)
        os.link(
            album / ms.orig_vid_dir / "clip1.mov",
            album / ms.vid_dir / "clip1.mov",
        )
        _write(album / ms.jpg_dir / "photo1.jpg", "d" * 60)
        _write(album / ms.jpg_dir / "photo2.jpg", "e" * 50)

        seen: set[tuple[int, int]] = set()
        result = compute_media_source_stats(album, ms, seen)

        assert result.media_source_type == MediaSourceType.STD
        assert result.unique_pictures == 2  # from orig-img
        assert result.unique_videos == 1  # from orig-vid
        assert result.archive.file_count == 3  # orig-img(2) + orig-vid(1)
        assert result.original.file_count == 3  # img(2) + vid(1)
        assert result.derived.file_count == 2  # jpg(2)
        # On-disk should be less than apparent due to hardlinks
        assert result.total.on_disk_bytes < result.total.apparent_bytes

    def test_missing_optional_dirs(self, tmp_path: Path) -> None:
        """iOS source with no edit dirs should not fail."""
        album = tmp_path / "2024-07-14 - Test"
        _make_album(album)
        ms = MAIN_MEDIA_SOURCE
        _write(album / ms.orig_img_dir / "IMG_0001.HEIC", "x" * 50)
        (album / ms.img_dir).mkdir(parents=True, exist_ok=True)
        (album / ms.vid_dir).mkdir(parents=True, exist_ok=True)
        (album / ms.jpg_dir).mkdir(parents=True, exist_ok=True)

        seen: set[tuple[int, int]] = set()
        result = compute_media_source_stats(album, ms, seen)
        assert result.unique_pictures == 1
        assert result.archive.file_count == 1


# ---------------------------------------------------------------------------
# compute_album_stats
# ---------------------------------------------------------------------------


class TestComputeAlbumStats:
    def test_single_ios_source(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)
        result = compute_album_stats(album)

        assert result.album_name == "2024-07-14 - Hiking"
        assert result.album_year == "2024"
        assert len(result.by_media_source) == 1
        assert result.aggregate.media_source_count == 1
        assert result.aggregate.unique_pictures == 2
        assert result.aggregate.unique_videos == 1

    def test_mixed_ios_and_std(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Party"
        _setup_ios_album(album)
        # Add a std media source
        ms = std_media_source("nelu")
        _write(album / ms.img_dir / "photo1.heic", "x" * 100)
        _write(album / ms.jpg_dir / "photo1.jpg", "y" * 60)

        result = compute_album_stats(album)
        assert len(result.by_media_source) == 2
        assert result.aggregate.media_source_count == 2

        type_dict = dict(result.aggregate.by_media_source_type)
        assert type_dict[MediaSourceType.IOS] == 1
        assert type_dict[MediaSourceType.STD] == 1

        # 2 iOS pictures + 1 std picture
        assert result.aggregate.unique_pictures == 3

    def test_unparseable_name_raises(self, tmp_path: Path) -> None:
        album = tmp_path / "bad name"
        _make_album(album)
        ms = MAIN_MEDIA_SOURCE
        _write(album / ms.orig_img_dir / "IMG_0001.HEIC", "x")
        (album / ms.img_dir).mkdir(parents=True, exist_ok=True)
        (album / ms.vid_dir).mkdir(parents=True, exist_ok=True)
        (album / ms.jpg_dir).mkdir(parents=True, exist_ok=True)

        with pytest.raises(ValueError, match="cannot be parsed"):
            compute_album_stats(album)

    def test_on_disk_less_than_apparent_for_hardlinks(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Optimized"
        _setup_ios_album(album)
        result = compute_album_stats(album)
        assert (
            result.aggregate.total.on_disk_bytes < result.aggregate.total.apparent_bytes
        )


# ---------------------------------------------------------------------------
# gallery_stats_from_album_stats
# ---------------------------------------------------------------------------


class TestGalleryStats:
    def _make_simple_album(
        self, tmp_path: Path, name: str, img_size: int = 100
    ) -> AlbumStats:
        album = tmp_path / name
        _make_album(album)
        ms = MAIN_MEDIA_SOURCE
        _write(album / ms.orig_img_dir / "IMG_0001.HEIC", "x" * img_size)
        _write(album / ms.orig_img_dir / "IMG_0001.AAE", "a" * 10)
        (album / ms.edit_img_dir).mkdir(parents=True, exist_ok=True)
        (album / ms.img_dir).mkdir(parents=True, exist_ok=True)
        os.link(
            album / ms.orig_img_dir / "IMG_0001.HEIC",
            album / ms.img_dir / "IMG_0001.HEIC",
        )
        (album / ms.vid_dir).mkdir(parents=True, exist_ok=True)
        (album / ms.orig_vid_dir).mkdir(parents=True, exist_ok=True)
        (album / ms.jpg_dir).mkdir(parents=True, exist_ok=True)
        _write(album / ms.jpg_dir / "IMG_0001.jpg", "j" * 50)
        return compute_album_stats(album)

    def test_aggregation(self, tmp_path: Path) -> None:
        a1 = self._make_simple_album(tmp_path, "2024-07-14 - Album One")
        a2 = self._make_simple_album(tmp_path, "2024-08-01 - Album Two", img_size=200)
        result = gallery_stats_from_album_stats([a1, a2])

        assert result.album_count == 2
        assert result.aggregate.unique_pictures == 2  # 1 per album
        assert result.aggregate.media_source_count == 2

    def test_year_breakdown(self, tmp_path: Path) -> None:
        a1 = self._make_simple_album(tmp_path, "2024-07-14 - Summer")
        a2 = self._make_simple_album(tmp_path, "2024-08-01 - Late Summer")
        a3 = self._make_simple_album(tmp_path, "2025-01-10 - Winter")
        result = gallery_stats_from_album_stats([a1, a2, a3])

        assert len(result.by_year) == 2
        year_dict = {ys.year: ys for ys in result.by_year}
        assert year_dict["2024"].album_count == 2
        assert year_dict["2025"].album_count == 1

    def test_unique_media_source_names(self, tmp_path: Path) -> None:
        # Album 1: main (ios)
        a1 = self._make_simple_album(tmp_path, "2024-07-14 - A")

        # Album 2: main (ios) + nelu (std)
        album2 = tmp_path / "2024-07-15 - B"
        _make_album(album2)
        ms_main = MAIN_MEDIA_SOURCE
        _write(album2 / ms_main.orig_img_dir / "IMG_0001.HEIC", "x" * 50)
        (album2 / ms_main.edit_img_dir).mkdir(parents=True, exist_ok=True)
        (album2 / ms_main.img_dir).mkdir(parents=True, exist_ok=True)
        os.link(
            album2 / ms_main.orig_img_dir / "IMG_0001.HEIC",
            album2 / ms_main.img_dir / "IMG_0001.HEIC",
        )
        (album2 / ms_main.vid_dir).mkdir(parents=True, exist_ok=True)
        (album2 / ms_main.orig_vid_dir).mkdir(parents=True, exist_ok=True)
        (album2 / ms_main.jpg_dir).mkdir(parents=True, exist_ok=True)
        ms_nelu = std_media_source("nelu")
        _write(album2 / ms_nelu.img_dir / "photo1.heic", "n" * 30)
        (album2 / ms_nelu.jpg_dir).mkdir(parents=True, exist_ok=True)
        a2 = compute_album_stats(album2)

        result = gallery_stats_from_album_stats([a1, a2])
        assert set(result.unique_media_source_names) == {"main", "nelu"}

    def test_empty_gallery(self) -> None:
        result = gallery_stats_from_album_stats([])
        assert result.album_count == 0
        assert result.aggregate.total.file_count == 0
        assert result.by_year == ()
