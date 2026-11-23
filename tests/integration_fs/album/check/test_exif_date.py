from pathlib import Path

from photree.album.check.exif_date import (
    ExifMismatch,
    ExifTimestampCheck,
    check_exif_date_match,
)
from photree.album.exif_cache.protocol import (
    EXIF_CACHE_VERSION,
    ExifCache,
    ExifCacheEntry,
)
from photree.album.exif_cache.store import save_exif_cache
from tests.fakes import FakeExifTool
from tests.testkit import write_file

_ON_DATE = "2024:07:14 10:00:00"
_OFF_DATE = "2023:01:01 10:00:00"


def _std_album(album: Path) -> None:
    write_file(album / "std-main" / "orig-img" / "DSC_0001.HEIC")
    write_file(album / "std-main" / "edit-img" / "DSC_0001.HEIC")
    write_file(album / "std-main" / "orig-vid" / "VID_0002.MOV")
    write_file(album / "main-img" / "DSC_0001.HEIC")
    write_file(album / "main-jpg" / "DSC_0001.jpg")
    write_file(album / "main-vid" / "VID_0002.MOV")


def _ios_album(album: Path) -> None:
    write_file(album / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    write_file(album / "ios-main" / "orig-img" / "IMG_0001.AAE")
    write_file(album / "ios-main" / "edit-img" / "IMG_E0001.HEIC")
    write_file(album / "ios-main" / "orig-vid" / "IMG_0002.MOV")
    write_file(album / "main-img" / "IMG_E0001.HEIC")
    write_file(album / "main-jpg" / "IMG_E0001.jpg")
    write_file(album / "main-vid" / "IMG_0002.MOV")


class TestExifTimestampCheck:
    def test_matches_when_nothing_is_wrong(self) -> None:
        assert ExifTimestampCheck(album_date="2024-07-14", mismatches=()).matches

    def test_does_not_match_with_a_mismatch(self) -> None:
        check = ExifTimestampCheck(
            album_date="2024-07-14",
            mismatches=(ExifMismatch(file_name="a.jpg", timestamp="2023-01-01"),),
        )
        assert not check.matches

    def test_does_not_match_without_an_exact_date_match(self) -> None:
        check = ExifTimestampCheck(
            album_date="2024-07-14",
            mismatches=(),
            no_exact_album_date_match=True,
        )
        assert not check.matches


class TestExactAlbumDateRule:
    # Both files fall on the day after the album date: in range (the next
    # day is tolerated), yet no file is on the album date itself.
    _NEXT_DAY = FakeExifTool(
        {"DSC_0001.jpg": "2024:07:15 10:00:00", "VID_0002.MOV": "2024:07:15 11:00:00"},
    )

    def test_single_day_album_needs_one_file_on_its_date(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(tmp_path, "2024-07-14", exiftool=self._NEXT_DAY)

        assert check is not None
        assert check.mismatches == ()
        assert check.no_exact_album_date_match
        assert not check.matches

    def test_continuation_part_is_exempt(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=self._NEXT_DAY,
            part="02",
        )

        assert check is not None
        assert check.matches

    def test_first_part_is_not_exempt(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=self._NEXT_DAY,
            part="01",
        )

        assert check is not None
        assert check.no_exact_album_date_match

    def test_range_album_is_exempt(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14--2024-07-15",
            exiftool=self._NEXT_DAY,
        )

        assert check is not None
        assert check.matches


class TestUpstreamFiles:
    def test_ios_image_upstream_is_the_archive(self, tmp_path: Path) -> None:
        _ios_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool(
                {"IMG_E0001.jpg": _OFF_DATE, "IMG_0002.MOV": _ON_DATE},
            ),
        )

        assert check is not None
        (mismatch,) = check.mismatches
        assert mismatch.file_name == "main-jpg/IMG_E0001.jpg"
        assert mismatch.upstream_files == (
            "ios-main/orig-img/IMG_0001.AAE",
            "ios-main/orig-img/IMG_0001.HEIC",
            "ios-main/edit-img/IMG_E0001.HEIC",
        )
        assert mismatch.is_ios

    def test_ios_video_upstream_is_the_archive(self, tmp_path: Path) -> None:
        _ios_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool(
                {"IMG_E0001.jpg": _ON_DATE, "IMG_0002.MOV": _OFF_DATE},
            ),
        )

        assert check is not None
        (mismatch,) = check.mismatches
        assert mismatch.upstream_files == ("ios-main/orig-vid/IMG_0002.MOV",)

    def test_album_without_media_source_has_no_upstream(self, tmp_path: Path) -> None:
        write_file(tmp_path / "loose" / "photo.jpg")

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool({"photo.jpg": _OFF_DATE}),
        )

        assert check is not None
        assert check.mismatches == (
            ExifMismatch(
                file_name="loose/photo.jpg",
                timestamp="2023-01-01T10:00:00",
            ),
        )

    def test_std_image_upstream_is_the_archive(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool(
                {"DSC_0001.jpg": _OFF_DATE, "VID_0002.MOV": _ON_DATE},
            ),
        )

        assert check is not None
        (mismatch,) = check.mismatches
        assert mismatch.file_name == "main-jpg/DSC_0001.jpg"
        assert mismatch.upstream_files == (
            "std-main/orig-img/DSC_0001.HEIC",
            "std-main/edit-img/DSC_0001.HEIC",
        )
        assert not mismatch.is_ios

    def test_std_video_upstream_is_the_archive(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool(
                {"DSC_0001.jpg": _ON_DATE, "VID_0002.MOV": _OFF_DATE},
            ),
        )

        assert check is not None
        (mismatch,) = check.mismatches
        assert mismatch.file_name == "main-vid/VID_0002.MOV"
        assert mismatch.upstream_files == ("std-main/orig-vid/VID_0002.MOV",)


class TestTimestampSource:
    def test_current_cache_is_read_instead_of_exiftool(self, tmp_path: Path) -> None:
        _std_album(tmp_path)
        save_exif_cache(
            tmp_path,
            "main",
            ExifCache(
                version=EXIF_CACHE_VERSION,
                files={
                    "main-jpg/DSC_0001": ExifCacheEntry(
                        mtime=0.0,
                        file_name="main-jpg/DSC_0001.jpg",
                        timestamp="2023-01-01T10:00:00",
                    ),
                },
            ),
        )

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool({"DSC_0001.jpg": _ON_DATE}),
        )

        assert check is not None
        assert [m.file_name for m in check.mismatches] == ["main-jpg/DSC_0001.jpg"]

    def test_exiftool_is_read_without_a_cache(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        check = check_exif_date_match(
            tmp_path,
            "2024-07-14",
            exiftool=FakeExifTool({"DSC_0001.jpg": _ON_DATE, "VID_0002.MOV": _ON_DATE}),
        )

        assert check is not None
        assert check.matches

    def test_no_readable_timestamp_skips_the_check(self, tmp_path: Path) -> None:
        _std_album(tmp_path)

        assert (
            check_exif_date_match(tmp_path, "2024-07-14", exiftool=FakeExifTool({}))
            is None
        )


class TestInvalidAlbumDate:
    def test_exif_check_skipped_for_invalid_date(self, tmp_path: Path) -> None:
        assert check_exif_date_match(tmp_path, "2024-02-30") is None
