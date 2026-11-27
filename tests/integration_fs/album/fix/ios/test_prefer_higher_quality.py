from pathlib import Path

from photree.album.fix.ios import (
    prefer_higher_quality_when_dups,
)
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from tests.testkit import file_names, write_files

MC = MAIN_MEDIA_SOURCE


class TestPreferHigherQualityWhenDups:
    def test_removes_jpg_when_heic_exists(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.JPG", "IMG_0001.AAE"],
        )

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 1
        assert "IMG_0001.JPG" not in file_names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.AAE" in file_names(tmp_path / "ios-main/orig-img")

    def test_removes_across_all_image_dirs(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.JPG"])
        write_files(tmp_path / "main-img", ["IMG_0001.HEIC", "IMG_0001.JPG"])

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 2
        assert "IMG_0001.JPG" not in file_names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.JPG" not in file_names(tmp_path / "main-img")

    def test_keeps_jpg_without_heic_dup(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.JPG"])

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 0
        assert "IMG_0002.JPG" in file_names(tmp_path / "ios-main/orig-img")

    def test_removes_png_when_heic_exists(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.PNG"])

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 1
        assert "IMG_0001.PNG" not in file_names(tmp_path / "ios-main/orig-img")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 0

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.JPG"])

        result = prefer_higher_quality_when_dups(tmp_path, MC, dry_run=True)

        assert result.total == 1
        assert "IMG_0001.JPG" in file_names(tmp_path / "ios-main/orig-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 0


class TestPreferHigherQualityRanking:
    def test_keeps_only_dng_when_dng_and_heic(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0235.DNG", "IMG_0235.HEIC", "IMG_0235.JPG"],
        )

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert file_names(tmp_path / "ios-main/orig-img") == {"IMG_0235.DNG"}
        assert result.removed_by_dir == (
            ("orig-img", ("IMG_0235.HEIC", "IMG_0235.JPG")),
        )

    def test_keeps_heic_over_heif(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.HEIF"])

        prefer_higher_quality_when_dups(tmp_path, MC)

        assert file_names(tmp_path / "ios-main/orig-img") == {"IMG_0001.HEIC"}
