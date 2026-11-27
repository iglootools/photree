from pathlib import Path

import pytest

from photree.album.fix import (
    MissingArchiveError,
    rm_orphan,
)
from photree.album.store.media_source import MAIN_MEDIA_SOURCE, std_media_source
from tests.testkit import file_names, write_files

MC = MAIN_MEDIA_SOURCE


def _files(directory: Path) -> set[Path]:
    if not directory.is_dir():
        return set()
    return {f for f in directory.iterdir() if f.is_file()}


def _names(directory: Path) -> set[str]:
    return {f.name for f in _files(directory)}


STD = std_media_source("nelu")


class TestRmOrphanHeic:
    def test_removes_orphan_rendered_and_browsable(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.AAE"])
        write_files(
            tmp_path / "ios-main/edit-img",
            ["IMG_E0001.HEIC", "IMG_O0001.AAE", "IMG_E9999.HEIC"],
        )
        write_files(tmp_path / "main-img", ["IMG_E0001.HEIC", "IMG_E9999.HEIC"])
        write_files(tmp_path / "main-jpg", ["IMG_E0001.jpg", "IMG_E9999.jpg"])

        result = rm_orphan(tmp_path, MC)

        # 9999 has no orig → orphan
        assert result.heic.total > 0
        assert "IMG_E9999.HEIC" not in _names(tmp_path / "ios-main/edit-img")
        assert "IMG_E9999.HEIC" not in _names(tmp_path / "main-img")
        assert "IMG_E9999.jpg" not in _names(tmp_path / "main-jpg")
        # 0001 has orig → kept
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")
        assert "IMG_E0001.HEIC" in _names(tmp_path / "main-img")
        assert "IMG_E0001.jpg" in _names(tmp_path / "main-jpg")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        write_files(tmp_path / "main-img", ["IMG_E0001.HEIC"])

        result = rm_orphan(tmp_path, MC)

        assert result.heic.total == 0

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", [])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E9999.HEIC"])

        result = rm_orphan(tmp_path, MC, dry_run=True)

        assert result.heic.total > 0
        assert "IMG_E9999.HEIC" in _names(tmp_path / "ios-main/edit-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = rm_orphan(tmp_path, MC)

        assert result.heic.total == 0
        assert result.mov.total == 0


class TestRmOrphanMov:
    def test_removes_orphan_rendered_and_browsable_vid(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-vid", ["IMG_0001.MOV"])
        write_files(tmp_path / "ios-main/edit-vid", ["IMG_E0001.MOV", "IMG_E9999.MOV"])
        write_files(tmp_path / "main-vid", ["IMG_E0001.MOV", "IMG_E9999.MOV"])

        rm_orphan(tmp_path, MC)

        assert "IMG_E9999.MOV" not in _names(tmp_path / "ios-main/edit-vid")
        assert "IMG_E9999.MOV" not in _names(tmp_path / "main-vid")
        assert "IMG_E0001.MOV" in _names(tmp_path / "ios-main/edit-vid")
        assert "IMG_E0001.MOV" in _names(tmp_path / "main-vid")


class TestRmOrphanStd:
    def test_removes_orphan_edit_and_browsable(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(
            tmp_path / "std-nelu/edit-img",
            ["sunset.jpg", "orphan.jpg"],
        )
        write_files(tmp_path / "nelu-img", ["sunset.jpg", "orphan.jpg"])
        write_files(tmp_path / "nelu-jpg", ["sunset.jpg", "orphan.jpg"])

        result = rm_orphan(tmp_path, STD)

        assert result.heic.total > 0
        # orphan has no orig counterpart → removed
        assert "orphan.jpg" not in file_names(tmp_path / "std-nelu/edit-img")
        assert "orphan.jpg" not in file_names(tmp_path / "nelu-img")
        assert "orphan.jpg" not in file_names(tmp_path / "nelu-jpg")
        # sunset has orig → kept
        assert "sunset.jpg" in file_names(tmp_path / "std-nelu/edit-img")
        assert "sunset.jpg" in file_names(tmp_path / "nelu-img")
        assert "sunset.jpg" in file_names(tmp_path / "nelu-jpg")

    def test_removes_orphan_vid(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        write_files(tmp_path / "std-nelu/edit-vid", ["clip.mov", "orphan.mov"])
        write_files(tmp_path / "nelu-vid", ["clip.mov", "orphan.mov"])

        result = rm_orphan(tmp_path, STD)

        assert result.mov.total > 0
        assert "orphan.mov" not in file_names(tmp_path / "std-nelu/edit-vid")
        assert "orphan.mov" not in file_names(tmp_path / "nelu-vid")
        assert "clip.mov" in file_names(tmp_path / "std-nelu/edit-vid")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "std-nelu/edit-img", ["sunset.jpg"])
        write_files(tmp_path / "nelu-img", ["sunset.jpg"])

        result = rm_orphan(tmp_path, STD)

        assert result.heic.total == 0
        assert result.mov.total == 0

    def test_raises_when_archive_missing(self, tmp_path: Path) -> None:
        write_files(tmp_path / "nelu-img", ["sunset.heic"])

        with pytest.raises(MissingArchiveError) as exc_info:
            rm_orphan(tmp_path, STD)
        assert exc_info.value.archive_dir == "std-nelu"

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        """No crash when archive exists but downstream dirs don't."""
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        # No edit-img, nelu-img, or nelu-jpg

        result = rm_orphan(tmp_path, STD)

        assert result.heic.total == 0
