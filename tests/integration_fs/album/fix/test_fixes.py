"""Tests for photree.album.fix module (generic fix operations for all source types)."""

from pathlib import Path

import pytest

from photree.album.fix import (
    refresh_browsable,
    rm_orphan,
    rm_upstream,
)
from photree.fs import std_media_source

STD = std_media_source("nelu")


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    """Create a directory with the given filenames."""
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


def _names(directory: Path) -> set[str]:
    """Return filenames (names only) in a directory."""
    if not directory.is_dir():
        return set()
    return {f.name for f in directory.iterdir() if f.is_file()}


def _noop_convert(*args: object, **kwargs: object) -> None:
    """Stub for convert_file that does nothing (avoids calling sips)."""
    return None


# ---------------------------------------------------------------------------
# refresh_browsable — std sources
# ---------------------------------------------------------------------------


class TestRefreshBrowsableStd:
    def test_rebuilds_img_from_archive(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        _setup_dir(tmp_path / "std-nelu/edit-img", ["sunset.jpg"])

        result = refresh_browsable(tmp_path, STD, convert_file=_noop_convert)

        assert result.heic.copied == 2
        # Edit wins for sunset
        assert "sunset.jpg" in _names(tmp_path / "nelu-img")
        assert "sunset.heic" not in _names(tmp_path / "nelu-img")
        # Orig used for beach
        assert "beach.png" in _names(tmp_path / "nelu-img")

    def test_rebuilds_vid_from_archive(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        _setup_dir(tmp_path / "std-nelu/edit-vid", ["clip.mov"])

        result = refresh_browsable(tmp_path, STD, convert_file=_noop_convert)

        assert result.mov.copied == 1
        assert "clip.mov" in _names(tmp_path / "nelu-vid")

    def test_raises_for_legacy_std_without_archive(self, tmp_path: Path) -> None:
        """Legacy std sources (no std-{name}/ archive) must raise FileNotFoundError."""
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic"])

        with pytest.raises(FileNotFoundError, match="Archive directory"):
            refresh_browsable(tmp_path, STD)

    def test_deletes_existing_browsable_before_rebuild(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        _setup_dir(tmp_path / "nelu-img", ["stale.heic"])

        refresh_browsable(tmp_path, STD, convert_file=_noop_convert)

        assert "sunset.heic" in _names(tmp_path / "nelu-img")
        assert "stale.heic" not in _names(tmp_path / "nelu-img")


# ---------------------------------------------------------------------------
# rm_orphan — std sources
# ---------------------------------------------------------------------------


class TestRmOrphanStd:
    def test_removes_orphan_edit_and_browsable(self, tmp_path: Path) -> None:
        """Files in edit/browsable with no orig counterpart are removed."""
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        _setup_dir(
            tmp_path / "std-nelu/edit-img",
            ["sunset.jpg", "orphan.jpg"],
        )
        _setup_dir(tmp_path / "nelu-img", ["sunset.jpg", "orphan.jpg"])
        _setup_dir(tmp_path / "nelu-jpg", ["sunset.jpg", "orphan.jpg"])

        result = rm_orphan(tmp_path, STD)

        assert result.heic.total > 0
        # orphan has no orig counterpart → removed
        assert "orphan.jpg" not in _names(tmp_path / "std-nelu/edit-img")
        assert "orphan.jpg" not in _names(tmp_path / "nelu-img")
        assert "orphan.jpg" not in _names(tmp_path / "nelu-jpg")
        # sunset has orig → kept
        assert "sunset.jpg" in _names(tmp_path / "std-nelu/edit-img")
        assert "sunset.jpg" in _names(tmp_path / "nelu-img")
        assert "sunset.jpg" in _names(tmp_path / "nelu-jpg")

    def test_removes_orphan_vid(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        _setup_dir(tmp_path / "std-nelu/edit-vid", ["clip.mov", "orphan.mov"])
        _setup_dir(tmp_path / "nelu-vid", ["clip.mov", "orphan.mov"])

        result = rm_orphan(tmp_path, STD)

        assert result.mov.total > 0
        assert "orphan.mov" not in _names(tmp_path / "std-nelu/edit-vid")
        assert "orphan.mov" not in _names(tmp_path / "nelu-vid")
        assert "clip.mov" in _names(tmp_path / "std-nelu/edit-vid")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        _setup_dir(tmp_path / "std-nelu/edit-img", ["sunset.jpg"])
        _setup_dir(tmp_path / "nelu-img", ["sunset.jpg"])

        result = rm_orphan(tmp_path, STD)

        assert result.heic.total == 0
        assert result.mov.total == 0

    def test_raises_for_legacy_std(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic"])

        with pytest.raises(FileNotFoundError, match="Archive directory"):
            rm_orphan(tmp_path, STD)

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        """No crash when archive exists but downstream dirs don't."""
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        # No edit-img, nelu-img, or nelu-jpg

        result = rm_orphan(tmp_path, STD)

        assert result.heic.total == 0


# ---------------------------------------------------------------------------
# rm_upstream — std sources
# ---------------------------------------------------------------------------


class TestRmUpstreamStd:
    def test_removes_upstream_when_jpeg_deleted(self, tmp_path: Path) -> None:
        """Deleting from nelu-jpg propagates to all upstream dirs."""
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        _setup_dir(tmp_path / "std-nelu/edit-img", ["sunset.jpg"])
        _setup_dir(tmp_path / "nelu-img", ["sunset.jpg"])
        # nelu-jpg is empty — jpeg was "deleted" by the user
        _setup_dir(tmp_path / "nelu-jpg", [])

        result = rm_upstream(tmp_path, STD)

        assert result.heic.removed_browsable == ("sunset.jpg",)
        assert result.heic.removed_rendered == ("sunset.jpg",)
        assert result.heic.removed_orig == ("sunset.heic",)
        assert _names(tmp_path / "nelu-img") == set()
        assert _names(tmp_path / "std-nelu/edit-img") == set()
        assert _names(tmp_path / "std-nelu/orig-img") == set()

    def test_keeps_files_with_jpeg_present(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic", "beach.png"])
        # Only sunset.jpg present — beach was deleted
        _setup_dir(tmp_path / "nelu-jpg", ["sunset.jpg"])

        result = rm_upstream(tmp_path, STD)

        assert "beach.png" in [f for f in result.heic.removed_orig]
        assert "sunset.heic" in _names(tmp_path / "std-nelu/orig-img")
        assert "beach.png" not in _names(tmp_path / "std-nelu/orig-img")

    def test_removes_upstream_when_browsable_img_deleted(self, tmp_path: Path) -> None:
        """Deleting from nelu-img propagates to jpeg and upstream dirs."""
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        # User deleted sunset from nelu-img
        _setup_dir(tmp_path / "nelu-img", ["beach.png"])
        _setup_dir(tmp_path / "nelu-jpg", ["sunset.jpg", "beach.png"])

        result = rm_upstream(tmp_path, STD)

        assert result.heic.removed_jpeg == ("sunset.jpg",)
        assert result.heic.removed_orig == ("sunset.heic",)
        assert "beach.png" in _names(tmp_path / "std-nelu/orig-img")

    def test_video_upstream_propagation(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-vid", ["clip.mov", "other.mov"])
        _setup_dir(tmp_path / "std-nelu/edit-vid", ["clip.mov"])
        # User deleted other.mov from nelu-vid
        _setup_dir(tmp_path / "nelu-vid", ["clip.mov"])

        result = rm_upstream(tmp_path, STD)

        assert result.mov.removed_orig == ("other.mov",)
        assert "clip.mov" in _names(tmp_path / "std-nelu/orig-vid")
        assert "other.mov" not in _names(tmp_path / "std-nelu/orig-vid")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic"])
        _setup_dir(tmp_path / "nelu-jpg", ["sunset.jpg"])

        result = rm_upstream(tmp_path, STD)

        assert result.heic.removed_browsable == ()
        assert result.heic.removed_rendered == ()
        assert result.heic.removed_orig == ()

    def test_raises_for_legacy_std(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic"])

        with pytest.raises(FileNotFoundError, match="Archive directory"):
            rm_upstream(tmp_path, STD)

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        """No crash when archive exists but no browsable dirs."""
        _setup_dir(tmp_path / "std-nelu/orig-img", [])

        result = rm_upstream(tmp_path, STD)

        assert result.heic.removed_browsable == ()
        assert result.mov.removed_orig == ()

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        _setup_dir(tmp_path / "nelu-img", ["sunset.heic"])
        _setup_dir(tmp_path / "nelu-jpg", [])

        result = rm_upstream(tmp_path, STD, dry_run=True)

        assert result.heic.removed_browsable == ("sunset.heic",)
        # Files still exist
        assert "sunset.heic" in _names(tmp_path / "std-nelu/orig-img")
        assert "sunset.heic" in _names(tmp_path / "nelu-img")
