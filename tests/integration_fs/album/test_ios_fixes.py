"""Tests for photree.album.ios_fixes module."""

from pathlib import Path

from photree.album.fixes import (
    rm_orphan,
    rm_upstream,
)
from photree.album.ios_fixes import (
    mv_miscategorized,
    prefer_higher_quality_when_dups,
    rm_miscategorized,
    rm_miscategorized_safe,
    rm_orphan_sidecar,
)
from photree.fs import MAIN_MEDIA_SOURCE

MC = MAIN_MEDIA_SOURCE


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    """Create a directory with the given filenames."""
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


def _files(directory: Path) -> set[str]:
    """Return filenames in a directory."""
    if not directory.is_dir():
        return set()
    return {f for f in directory.iterdir() if f.is_file()}


def _names(directory: Path) -> set[str]:
    """Return filenames (names only) in a directory."""
    return {f.name for f in _files(directory)}


class TestRmUpstreamHeic:
    def test_removes_upstream_when_jpeg_deleted(self, tmp_path: Path) -> None:
        """Deleting a file from main-jpg propagates to all upstream dirs."""
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0410.HEIC", "IMG_0410.AAE"])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0410.HEIC", "IMG_O0410.AAE"])
        _setup_dir(tmp_path / "main-img", ["IMG_E0410.HEIC"])
        # main-jpg is empty — the jpeg was "deleted" by the user
        _setup_dir(tmp_path / "main-jpg", [])

        result = rm_upstream(tmp_path, MC)

        assert result.heic.removed_browsable == ("IMG_E0410.HEIC",)
        assert set(result.heic.removed_rendered) == {"IMG_E0410.HEIC", "IMG_O0410.AAE"}
        assert set(result.heic.removed_orig) == {"IMG_0410.HEIC", "IMG_0410.AAE"}
        assert _names(tmp_path / "main-img") == set()
        assert _names(tmp_path / "ios-main/edit-img") == set()
        assert _names(tmp_path / "ios-main/orig-img") == set()

    def test_keeps_files_with_jpeg_present(self, tmp_path: Path) -> None:
        """Files with a matching jpeg are kept."""
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0002.HEIC"],
        )
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])
        # Only IMG_0001.jpg present — IMG_0002 was deleted
        _setup_dir(tmp_path / "main-jpg", ["IMG_0001.jpg"])

        result = rm_upstream(tmp_path, MC)

        assert result.heic.removed_browsable == ("IMG_0002.HEIC",)
        assert "IMG_0002.HEIC" not in _names(tmp_path / "ios-main/orig-img")
        # IMG_0001 files are untouched
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.AAE" in _names(tmp_path / "ios-main/orig-img")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        """No deletions when all jpegs are present."""
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "main-jpg", ["IMG_0001.jpg"])

        result = rm_upstream(tmp_path, MC)

        assert result.heic.removed_browsable == ()
        assert result.heic.removed_rendered == ()
        assert result.heic.removed_orig == ()

    def test_handles_jpg_copy_as_is(self, tmp_path: Path) -> None:
        """JPG files in main-img are copied as-is to main-jpg."""
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.JPG"])
        _setup_dir(tmp_path / "main-img", ["IMG_0001.JPG"])
        # JPG was deleted from main-jpg
        _setup_dir(tmp_path / "main-jpg", [])

        result = rm_upstream(tmp_path, MC)

        assert result.heic.removed_browsable == ("IMG_0001.JPG",)

    def test_removes_upstream_when_browsable_heic_deleted(self, tmp_path: Path) -> None:
        """Deleting a file from main-img propagates to jpeg and upstream dirs."""
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_0002.HEIC", "IMG_0002.AAE"],
        )
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC", "IMG_O0001.AAE"])
        # User deleted IMG_E0001.HEIC from main-img
        _setup_dir(tmp_path / "main-img", ["IMG_0002.HEIC"])
        _setup_dir(tmp_path / "main-jpg", ["IMG_E0001.jpg", "IMG_0002.jpg"])

        result = rm_upstream(tmp_path, MC)

        # main-jpg: IMG_E0001.jpg removed
        assert result.heic.removed_jpeg == ("IMG_E0001.jpg",)
        # main-img: nothing extra to remove (already deleted by user)
        assert result.heic.removed_browsable == ()
        # upstream: orig and rendered for number 0001 removed
        assert set(result.heic.removed_rendered) == {"IMG_E0001.HEIC", "IMG_O0001.AAE"}
        assert set(result.heic.removed_orig) == {"IMG_0001.HEIC", "IMG_0001.AAE"}
        # IMG_0002 files untouched
        assert "IMG_0002.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0002.HEIC" in _names(tmp_path / "main-img")
        assert "IMG_0002.jpg" in _names(tmp_path / "main-jpg")

    def test_both_jpeg_and_heic_deletions_merged(self, tmp_path: Path) -> None:
        """Deletions from both main-jpg and main-img are merged."""
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0002.HEIC", "IMG_0003.HEIC"],
        )
        # IMG_0002 deleted from main-img, IMG_0003 jpeg deleted from main-jpg
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC", "IMG_0003.HEIC"])
        _setup_dir(tmp_path / "main-jpg", ["IMG_0001.jpg"])

        result = rm_upstream(tmp_path, MC)

        removed_numbers = {
            "".join(c for c in f if c.isdigit()) for f in result.heic.removed_orig
        }
        assert "0002" in removed_numbers
        assert "0003" in removed_numbers
        assert "0001" not in removed_numbers

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "main-jpg", [])

        result = rm_upstream(tmp_path, MC, dry_run=True)

        assert result.heic.removed_browsable == ("IMG_0001.HEIC",)
        # Files still exist
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" in _names(tmp_path / "main-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        """No crash when directories don't exist."""
        result = rm_upstream(tmp_path, MC)

        assert result.heic.removed_browsable == ()
        assert result.mov.removed_orig == ()


class TestRmUpstreamMov:
    def test_removes_upstream_when_browsable_mov_deleted(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-vid", ["IMG_0115.MOV"])
        _setup_dir(tmp_path / "ios-main/edit-vid", ["IMG_E0115.MOV"])
        _setup_dir(tmp_path / "main-vid", [])

        result = rm_upstream(tmp_path, MC)

        assert result.mov.removed_rendered == ("IMG_E0115.MOV",)
        assert result.mov.removed_orig == ("IMG_0115.MOV",)
        assert _names(tmp_path / "ios-main/edit-vid") == set()
        assert _names(tmp_path / "ios-main/orig-vid") == set()

    def test_keeps_files_with_browsable_mov_present(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-vid", ["IMG_0001.MOV", "IMG_0002.MOV"])
        _setup_dir(tmp_path / "ios-main/edit-vid", ["IMG_E0001.MOV"])
        _setup_dir(tmp_path / "main-vid", ["IMG_E0001.MOV"])

        result = rm_upstream(tmp_path, MC)

        # IMG_0002 was removed from main-vid → propagate
        assert result.mov.removed_orig == ("IMG_0002.MOV",)
        # IMG_0001 untouched
        assert "IMG_0001.MOV" in _names(tmp_path / "ios-main/orig-vid")
        assert "IMG_E0001.MOV" in _names(tmp_path / "ios-main/edit-vid")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-vid", ["IMG_0001.MOV"])
        _setup_dir(tmp_path / "main-vid", ["IMG_0001.MOV"])

        result = rm_upstream(tmp_path, MC)

        assert result.mov.removed_rendered == ()
        assert result.mov.removed_orig == ()


# ---------------------------------------------------------------------------
# rm_orphan
# ---------------------------------------------------------------------------


class TestRmOrphanHeic:
    def test_removes_orphan_rendered_and_browsable(self, tmp_path: Path) -> None:
        """Files in rendered/browsable with no orig counterpart are removed."""
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.AAE"])
        _setup_dir(
            tmp_path / "ios-main/edit-img",
            ["IMG_E0001.HEIC", "IMG_O0001.AAE", "IMG_E9999.HEIC"],
        )
        _setup_dir(tmp_path / "main-img", ["IMG_E0001.HEIC", "IMG_E9999.HEIC"])
        _setup_dir(tmp_path / "main-jpg", ["IMG_E0001.jpg", "IMG_E9999.jpg"])

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
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        _setup_dir(tmp_path / "main-img", ["IMG_E0001.HEIC"])

        result = rm_orphan(tmp_path, MC)

        assert result.heic.total == 0

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", [])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E9999.HEIC"])

        result = rm_orphan(tmp_path, MC, dry_run=True)

        assert result.heic.total > 0
        assert "IMG_E9999.HEIC" in _names(tmp_path / "ios-main/edit-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = rm_orphan(tmp_path, MC)

        assert result.heic.total == 0
        assert result.mov.total == 0


class TestRmOrphanMov:
    def test_removes_orphan_rendered_and_browsable_mov(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-vid", ["IMG_0001.MOV"])
        _setup_dir(tmp_path / "ios-main/edit-vid", ["IMG_E0001.MOV", "IMG_E9999.MOV"])
        _setup_dir(tmp_path / "main-vid", ["IMG_E0001.MOV", "IMG_E9999.MOV"])

        rm_orphan(tmp_path, MC)

        assert "IMG_E9999.MOV" not in _names(tmp_path / "ios-main/edit-vid")
        assert "IMG_E9999.MOV" not in _names(tmp_path / "main-vid")
        assert "IMG_E0001.MOV" in _names(tmp_path / "ios-main/edit-vid")
        assert "IMG_E0001.MOV" in _names(tmp_path / "main-vid")


# ---------------------------------------------------------------------------
# rm_orphan_sidecar
# ---------------------------------------------------------------------------


class TestRmOrphanSidecar:
    def test_removes_orphan_aae_in_orig(self, tmp_path: Path) -> None:
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_9999.AAE"],
        )
        _setup_dir(tmp_path / "ios-main/edit-img", [])

        result = rm_orphan_sidecar(tmp_path, MC)
        assert result.total == 1
        assert not (tmp_path / "ios-main/orig-img" / "IMG_9999.AAE").exists()
        assert (tmp_path / "ios-main/orig-img" / "IMG_0001.AAE").exists()

    def test_removes_orphan_o_aae_in_rendered(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.AAE"])
        _setup_dir(
            tmp_path / "ios-main/edit-img",
            ["IMG_E0001.HEIC", "IMG_O0001.AAE", "IMG_O9999.AAE"],
        )

        result = rm_orphan_sidecar(tmp_path, MC)
        assert result.total == 1
        assert not (tmp_path / "ios-main/edit-img" / "IMG_O9999.AAE").exists()
        assert (tmp_path / "ios-main/edit-img" / "IMG_O0001.AAE").exists()

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.AAE"])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC", "IMG_O0001.AAE"])

        result = rm_orphan_sidecar(tmp_path, MC)
        assert result.total == 0

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_9999.AAE"])
        _setup_dir(tmp_path / "ios-main/edit-img", [])

        result = rm_orphan_sidecar(tmp_path, MC, dry_run=True)
        assert result.total == 1
        assert (tmp_path / "ios-main/orig-img" / "IMG_9999.AAE").exists()

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = rm_orphan_sidecar(tmp_path, MC)
        assert result.total == 0


# ---------------------------------------------------------------------------
# prefer_higher_quality_when_dups
# ---------------------------------------------------------------------------


class TestPreferHigherQualityWhenDups:
    def test_removes_jpg_when_heic_exists(self, tmp_path: Path) -> None:
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.JPG", "IMG_0001.AAE"],
        )

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 1
        assert "IMG_0001.JPG" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.AAE" in _names(tmp_path / "ios-main/orig-img")

    def test_removes_across_all_image_dirs(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.JPG"])
        _setup_dir(tmp_path / "main-img", ["IMG_0001.HEIC", "IMG_0001.JPG"])

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 2
        assert "IMG_0001.JPG" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.JPG" not in _names(tmp_path / "main-img")

    def test_keeps_jpg_without_heic_dup(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.JPG"])

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 0
        assert "IMG_0002.JPG" in _names(tmp_path / "ios-main/orig-img")

    def test_removes_png_when_heic_exists(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.PNG"])

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 1
        assert "IMG_0001.PNG" not in _names(tmp_path / "ios-main/orig-img")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0002.HEIC"])

        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 0

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.JPG"])

        result = prefer_higher_quality_when_dups(tmp_path, MC, dry_run=True)

        assert result.total == 1
        assert "IMG_0001.JPG" in _names(tmp_path / "ios-main/orig-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = prefer_higher_quality_when_dups(tmp_path, MC)

        assert result.total == 0


# ---------------------------------------------------------------------------
# rm_miscategorized / mv_miscategorized
# ---------------------------------------------------------------------------


class TestRmMiscategorized:
    def test_removes_rendered_from_orig(self, tmp_path: Path) -> None:
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_E0001.HEIC", "IMG_O0001.AAE"],
        )
        _setup_dir(tmp_path / "ios-main/edit-img", [])

        result = rm_miscategorized(tmp_path, MC)

        assert set(result.heic.fixed_from_orig) == {"IMG_E0001.HEIC", "IMG_O0001.AAE"}
        assert "IMG_E0001.HEIC" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_O0001.AAE" not in _names(tmp_path / "ios-main/orig-img")
        # Originals untouched
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.AAE" in _names(tmp_path / "ios-main/orig-img")

    def test_removes_original_from_rendered(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", [])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])

        result = rm_miscategorized(tmp_path, MC)

        assert result.heic.fixed_from_rendered == ("IMG_0001.HEIC",)
        assert "IMG_0001.HEIC" not in _names(tmp_path / "ios-main/edit-img")
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])

        result = rm_miscategorized(tmp_path, MC)

        assert result.total == 0

    def test_mov_dirs(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-vid", ["IMG_E0001.MOV"])
        _setup_dir(tmp_path / "ios-main/edit-vid", [])

        result = rm_miscategorized(tmp_path, MC)

        assert result.mov.fixed_from_orig == ("IMG_E0001.MOV",)

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_E0001.HEIC"])
        _setup_dir(tmp_path / "ios-main/edit-img", [])

        result = rm_miscategorized(tmp_path, MC, dry_run=True)

        assert result.total == 1
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/orig-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = rm_miscategorized(tmp_path, MC)

        assert result.total == 0


class TestRmMiscategorizedSafe:
    def test_removes_when_present_in_correct_dir(self, tmp_path: Path) -> None:
        """Deletes miscategorized file only if it already exists in the correct dir."""
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])

        result = rm_miscategorized_safe(tmp_path, MC)

        assert result.heic.fixed_from_orig == ("IMG_E0001.HEIC",)
        assert "IMG_E0001.HEIC" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")

    def test_keeps_when_not_present_in_correct_dir(self, tmp_path: Path) -> None:
        """Does NOT delete miscategorized file if it's missing from the correct dir."""
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_E0001.HEIC"])
        _setup_dir(tmp_path / "ios-main/edit-img", [])

        result = rm_miscategorized_safe(tmp_path, MC)

        assert result.total == 0
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/orig-img")

    def test_both_directions(self, tmp_path: Path) -> None:
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_E0001.HEIC", "IMG_E0002.HEIC"],
        )
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC", "IMG_0099.HEIC"])
        _setup_dir(
            tmp_path / "ios-main/orig-img", ["IMG_0099.HEIC"]
        )  # 0099 exists in orig too

        result = rm_miscategorized_safe(tmp_path, MC)

        # IMG_E0001 is in rendered → safe to remove from orig
        assert "IMG_E0001.HEIC" in result.heic.fixed_from_orig
        # IMG_E0002 is NOT in rendered → kept in orig
        assert "IMG_E0002.HEIC" not in result.heic.fixed_from_orig
        # IMG_0099 is in orig → safe to remove from rendered
        assert "IMG_0099.HEIC" in result.heic.fixed_from_rendered

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = rm_miscategorized_safe(tmp_path, MC)

        assert result.total == 0


class TestMvMiscategorized:
    def test_moves_rendered_from_orig_to_rendered(self, tmp_path: Path) -> None:
        _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_E0001.HEIC", "IMG_O0001.AAE"],
        )
        _setup_dir(tmp_path / "ios-main/edit-img", [])

        result = mv_miscategorized(tmp_path, MC)

        assert set(result.heic.fixed_from_orig) == {"IMG_E0001.HEIC", "IMG_O0001.AAE"}
        # Moved to rendered
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")
        assert "IMG_O0001.AAE" in _names(tmp_path / "ios-main/edit-img")
        # Gone from orig
        assert "IMG_E0001.HEIC" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_O0001.AAE" not in _names(tmp_path / "ios-main/orig-img")
        # Original stays
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")

    def test_moves_original_from_rendered_to_orig(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", [])
        _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_0001.HEIC"])

        result = mv_miscategorized(tmp_path, MC)

        assert result.heic.fixed_from_rendered == ("IMG_0001.HEIC",)
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" not in _names(tmp_path / "ios-main/edit-img")

    def test_creates_target_dir_if_missing(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_E0001.HEIC"])
        # ios/edit-img doesn't exist

        result = mv_miscategorized(tmp_path, MC)

        assert result.heic.fixed_from_orig == ("IMG_E0001.HEIC",)
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_E0001.HEIC"])
        _setup_dir(tmp_path / "ios-main/edit-img", [])

        result = mv_miscategorized(tmp_path, MC, dry_run=True)

        assert result.total == 1
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_E0001.HEIC" not in _names(tmp_path / "ios-main/edit-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = mv_miscategorized(tmp_path, MC)

        assert result.total == 0
