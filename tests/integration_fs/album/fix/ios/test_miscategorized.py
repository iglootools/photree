from pathlib import Path

import pytest

from photree.album.fix.ios import (
    MiscategorizedAction,
    MiscategorizedMoveConflictError,
    run_fix_ios,
)
from photree.album.fix.ios.miscategorized import fix_miscategorized
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from tests.testkit import file_names, write_files

MC = MAIN_MEDIA_SOURCE


def _files(directory: Path) -> set[Path]:
    if not directory.is_dir():
        return set()
    return {f for f in directory.iterdir() if f.is_file()}


def _names(directory: Path) -> set[str]:
    return {f.name for f in _files(directory)}


class TestRmMiscategorized:
    def test_removes_rendered_from_orig(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_E0001.HEIC", "IMG_O0001.AAE"],
        )
        write_files(tmp_path / "ios-main/edit-img", [])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM,
            dry_run=False,
        )

        assert set(result.heic.fixed_from_orig) == {"IMG_E0001.HEIC", "IMG_O0001.AAE"}
        assert "IMG_E0001.HEIC" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_O0001.AAE" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.AAE" in _names(tmp_path / "ios-main/orig-img")

    def test_removes_original_from_rendered(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", [])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM,
            dry_run=False,
        )

        assert result.heic.fixed_from_rendered == ("IMG_0001.HEIC",)
        assert "IMG_0001.HEIC" not in _names(tmp_path / "ios-main/edit-img")
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM,
            dry_run=False,
        )

        assert result.total == 0

    def test_mov_dirs(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-vid", ["IMG_E0001.MOV"])
        write_files(tmp_path / "ios-main/edit-vid", [])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM,
            dry_run=False,
        )

        assert result.mov.fixed_from_orig == ("IMG_E0001.MOV",)

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", [])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM,
            dry_run=True,
        )

        assert result.total == 1
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/orig-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM,
            dry_run=False,
        )

        assert result.total == 0


class TestRmMiscategorizedSafe:
    def test_removes_when_present_in_correct_dir(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM_SAFE,
            dry_run=False,
        )

        assert result.heic.fixed_from_orig == ("IMG_E0001.HEIC",)
        assert "IMG_E0001.HEIC" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")

    def test_keeps_when_not_present_in_correct_dir(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", [])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM_SAFE,
            dry_run=False,
        )

        assert result.total == 0
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/orig-img")

    def test_both_directions(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_E0001.HEIC", "IMG_E0002.HEIC"],
        )
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC", "IMG_0099.HEIC"])
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0099.HEIC"],
        )  # 0099 exists in orig too

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM_SAFE,
            dry_run=False,
        )

        # IMG_E0001 is in rendered → safe to remove from orig
        assert "IMG_E0001.HEIC" in result.heic.fixed_from_orig
        # IMG_E0002 is NOT in rendered → kept in orig
        assert "IMG_E0002.HEIC" not in result.heic.fixed_from_orig
        # IMG_0099 is in orig → safe to remove from rendered
        assert "IMG_0099.HEIC" in result.heic.fixed_from_rendered

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.RM_SAFE,
            dry_run=False,
        )

        assert result.total == 0


class TestMvMiscategorized:
    def test_moves_rendered_from_orig_to_rendered(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_E0001.HEIC", "IMG_O0001.AAE"],
        )
        write_files(tmp_path / "ios-main/edit-img", [])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.MV,
            dry_run=False,
        )

        assert set(result.heic.fixed_from_orig) == {"IMG_E0001.HEIC", "IMG_O0001.AAE"}
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")
        assert "IMG_O0001.AAE" in _names(tmp_path / "ios-main/edit-img")
        assert "IMG_E0001.HEIC" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_O0001.AAE" not in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")

    def test_moves_original_from_rendered_to_orig(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", [])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_0001.HEIC"])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.MV,
            dry_run=False,
        )

        assert result.heic.fixed_from_rendered == ("IMG_0001.HEIC",)
        assert "IMG_0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_0001.HEIC" not in _names(tmp_path / "ios-main/edit-img")

    def test_creates_target_dir_if_missing(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_E0001.HEIC"])
        # ios/edit-img doesn't exist

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.MV,
            dry_run=False,
        )

        assert result.heic.fixed_from_orig == ("IMG_E0001.HEIC",)
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/edit-img")

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", [])

        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.MV,
            dry_run=True,
        )

        assert result.total == 1
        assert "IMG_E0001.HEIC" in _names(tmp_path / "ios-main/orig-img")
        assert "IMG_E0001.HEIC" not in _names(tmp_path / "ios-main/edit-img")

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        [result] = fix_miscategorized(
            tmp_path,
            [MC],
            action=MiscategorizedAction.MV,
            dry_run=False,
        )

        assert result.total == 0


class TestMvMiscategorizedOverwrite:
    def test_refuses_to_overwrite_existing_target(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        (tmp_path / "ios-main/edit-img/IMG_E0001.HEIC").write_text("keep-me")

        with pytest.raises(MiscategorizedMoveConflictError) as exc_info:
            fix_miscategorized(
                tmp_path,
                [MC],
                action=MiscategorizedAction.MV,
                dry_run=False,
            )

        assert exc_info.value.target_dir == "ios-main/edit-img"
        assert exc_info.value.conflicts == ("IMG_E0001.HEIC",)
        content = (tmp_path / "ios-main/edit-img/IMG_E0001.HEIC").read_text()
        assert content == "keep-me"
        assert "IMG_E0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")

    def test_video_conflict_leaves_images_unmoved(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-main/orig-vid", ["IMG_0002.MOV", "IMG_E0002.MOV"])
        write_files(tmp_path / "ios-main/edit-vid", ["IMG_E0002.MOV"])

        with pytest.raises(MiscategorizedMoveConflictError) as exc_info:
            fix_miscategorized(
                tmp_path,
                [MC],
                action=MiscategorizedAction.MV,
                dry_run=False,
            )

        assert exc_info.value.target_dir == "ios-main/edit-vid"
        assert "IMG_E0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")
        assert file_names(tmp_path / "ios-main/edit-img") == set()

    def test_conflict_in_one_source_leaves_every_source_unmoved(
        self,
        tmp_path: Path,
    ) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
        write_files(tmp_path / "ios-nelu/orig-img", ["IMG_0002.HEIC", "IMG_E0002.HEIC"])
        write_files(tmp_path / "ios-nelu/edit-img", ["IMG_E0002.HEIC"])

        with pytest.raises(MiscategorizedMoveConflictError) as exc_info:
            run_fix_ios(tmp_path, dry_run=False, mv_miscategorized=True)

        assert exc_info.value.target_dir == "ios-nelu/edit-img"
        assert "IMG_E0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")
        assert file_names(tmp_path / "ios-main/edit-img") == set()
