from pathlib import Path

import pytest

from photree.album.fix import (
    MissingArchiveError,
    rm_orphan,
    rm_upstream,
)
from photree.album.store.media_source import std_media_source
from tests.testkit import file_names, write_files

STD = std_media_source("nelu")


# ---------------------------------------------------------------------------


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


class TestRmUpstreamStd:
    def test_removes_upstream_when_jpeg_deleted(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "std-nelu/edit-img", ["sunset.jpg"])
        write_files(tmp_path / "nelu-img", ["sunset.jpg"])
        # nelu-jpg is empty — jpeg was "deleted" by the user
        write_files(tmp_path / "nelu-jpg", [])

        # The only image deleted everywhere: needs --force (would empty the archive)
        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=True)

        assert result.heic.removed_browsable == ("sunset.jpg",)
        assert result.heic.removed_rendered == ("sunset.jpg",)
        assert result.heic.removed_orig == ("sunset.heic",)
        assert file_names(tmp_path / "nelu-img") == set()
        assert file_names(tmp_path / "std-nelu/edit-img") == set()
        assert file_names(tmp_path / "std-nelu/orig-img") == set()

    def test_keeps_files_with_jpeg_present(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        write_files(tmp_path / "nelu-img", ["sunset.heic", "beach.png"])
        # Only sunset.jpg present — beach was deleted
        write_files(tmp_path / "nelu-jpg", ["sunset.jpg"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert "beach.png" in result.heic.removed_orig
        assert "sunset.heic" in file_names(tmp_path / "std-nelu/orig-img")
        assert "beach.png" not in file_names(tmp_path / "std-nelu/orig-img")

    def test_removes_upstream_when_browsable_img_deleted(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        # User deleted sunset from nelu-img
        write_files(tmp_path / "nelu-img", ["beach.png"])
        write_files(tmp_path / "nelu-jpg", ["sunset.jpg", "beach.png"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.heic.removed_jpeg == ("sunset.jpg",)
        assert result.heic.removed_orig == ("sunset.heic",)
        assert "beach.png" in file_names(tmp_path / "std-nelu/orig-img")

    def test_video_upstream_propagation(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov", "other.mov"])
        write_files(tmp_path / "std-nelu/edit-vid", ["clip.mov"])
        # User deleted other.mov from nelu-vid
        write_files(tmp_path / "nelu-vid", ["clip.mov"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.mov.removed_orig == ("other.mov",)
        assert "clip.mov" in file_names(tmp_path / "std-nelu/orig-vid")
        assert "other.mov" not in file_names(tmp_path / "std-nelu/orig-vid")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-jpg", ["sunset.jpg"])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.heic.removed_browsable == ()
        assert result.heic.removed_rendered == ()
        assert result.heic.removed_orig == ()

    def test_raises_when_archive_missing(self, tmp_path: Path) -> None:
        write_files(tmp_path / "nelu-img", ["sunset.heic"])

        with pytest.raises(MissingArchiveError) as exc_info:
            rm_upstream(tmp_path, [STD], dry_run=False, force=False)
        assert exc_info.value.archive_dir == "std-nelu"

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        """No crash when archive exists but no browsable dirs."""
        write_files(tmp_path / "std-nelu/orig-img", [])

        [result] = rm_upstream(tmp_path, [STD], dry_run=False, force=False)

        assert result.heic.removed_browsable == ()
        assert result.mov.removed_orig == ()

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-img", ["sunset.heic"])
        write_files(tmp_path / "nelu-jpg", [])

        [result] = rm_upstream(tmp_path, [STD], dry_run=True, force=True)

        assert result.heic.removed_browsable == ("sunset.heic",)
        assert "sunset.heic" in file_names(tmp_path / "std-nelu/orig-img")
        assert "sunset.heic" in file_names(tmp_path / "nelu-img")
