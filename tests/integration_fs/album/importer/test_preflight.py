"""Tests for photree.album.importer.preflight module."""

from pathlib import Path

from photree.album.importer.preflight import check_image_capture_dir, run_preflight
from photree.clihelpers.sysdeps import import_deps, refresh_deps
from photree.common.sysdeps import SystemDependency, SystemDependencyStatus


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


class TestSystemDeps:
    """``run_preflight`` folds caller-probed dependency statuses into its result.

    It takes them as a parameter rather than reading PATH, so these drive every
    branch directly.
    """

    def _ic_dir(self, tmp_path: Path) -> Path:
        _populate(tmp_path / "ic", ["IMG_0001.HEIC", "IMG_0001.AAE"])
        return tmp_path / "ic"

    def test_missing_dependency_fails_the_preflight(self, tmp_path: Path) -> None:
        result = run_preflight(
            self._ic_dir(tmp_path),
            system_deps=(
                SystemDependencyStatus(
                    dependency=SystemDependency.SIPS, available=True
                ),
                SystemDependencyStatus(
                    dependency=SystemDependency.EXIFTOOL, available=False
                ),
            ),
        )

        assert not result.success
        assert result.missing_system_deps == (SystemDependency.EXIFTOOL,)

    def test_all_present_passes(self, tmp_path: Path) -> None:
        result = run_preflight(
            self._ic_dir(tmp_path),
            system_deps=tuple(
                SystemDependencyStatus(dependency=d, available=True)
                for d in SystemDependency
            ),
        )

        assert result.success
        assert result.missing_system_deps == ()

    def test_does_not_read_path(self, tmp_path: Path, monkeypatch) -> None:
        """An empty PATH must not change the outcome — the caller owns probing."""
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))

        result = run_preflight(
            self._ic_dir(tmp_path),
            system_deps=(
                SystemDependencyStatus(
                    dependency=SystemDependency.EXIFTOOL, available=True
                ),
            ),
        )

        assert result.success


class TestImportDeps:
    def test_requires_both_by_default(self) -> None:
        assert set(import_deps()) == set(SystemDependency)

    def test_skip_heic_to_jpeg_drops_sips(self) -> None:
        assert import_deps(skip_heic_to_jpeg=True) == (SystemDependency.EXIFTOOL,)

    def test_refresh_matches_import(self) -> None:
        assert refresh_deps() == import_deps()
