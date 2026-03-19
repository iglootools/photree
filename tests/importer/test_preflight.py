"""Tests for photree.importer.preflight module."""

from pathlib import Path

from photree.importer.preflight import check_image_capture_dir


def _populate(path: Path, filenames: list[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text("data")


class TestCheckImageCaptureDir:
    def test_valid_directory_passes(self, tmp_path: Path) -> None:
        _populate(
            tmp_path,
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_E0001.HEIC", "IMG_O0001.AAE"],
        )
        result = check_image_capture_dir(tmp_path)
        assert result.success
        assert result.has_media_files
        assert not result.has_low_img_prefix_ratio
        assert not result.has_subdirectories

    def test_no_media_files_warns(self, tmp_path: Path) -> None:
        _populate(tmp_path, ["readme.txt", "notes.pdf"])
        result = check_image_capture_dir(tmp_path)
        assert not result.success
        assert not result.has_media_files

    def test_low_img_prefix_ratio_warns(self, tmp_path: Path) -> None:
        _populate(
            tmp_path,
            ["random1.HEIC", "random2.HEIC", "random3.HEIC", "IMG_0001.HEIC"],
        )
        result = check_image_capture_dir(tmp_path)
        assert not result.success
        assert result.has_low_img_prefix_ratio
        assert result.img_prefixed_count == 1
        assert result.total_file_count == 4

    def test_subdirectories_warns(self, tmp_path: Path) -> None:
        _populate(tmp_path, ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        (tmp_path / "subdir").mkdir()
        result = check_image_capture_dir(tmp_path)
        assert not result.success
        assert result.has_subdirectories
        assert "subdir" in result.subdirectory_names

    def test_mixed_with_enough_img_passes(self, tmp_path: Path) -> None:
        _populate(
            tmp_path,
            [
                "IMG_0001.HEIC",
                "IMG_0002.HEIC",
                "IMG_0003.MOV",
                "ABCD1234.JPG",
            ],
        )
        result = check_image_capture_dir(tmp_path)
        assert not result.has_low_img_prefix_ratio

    def test_empty_directory_warns(self, tmp_path: Path) -> None:
        result = check_image_capture_dir(tmp_path)
        assert not result.success
        assert not result.has_media_files
