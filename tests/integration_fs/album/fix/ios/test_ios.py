from pathlib import Path

from photree.album.fix.ios import (
    MiscategorizedAction,
    run_fix_ios,
)
from photree.album.fix.ios.output import format_fix_ios_result
from tests.testkit import file_names, write_files


def _two_sources_with_miscategorized_files(album: Path) -> None:
    """Edits in orig-img on main, an original in edit-img and a video on nelu."""
    write_files(album / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_E0001.HEIC"])
    write_files(album / "ios-main/edit-img", ["IMG_E0002.HEIC", "IMG_0003.HEIC"])
    write_files(album / "ios-nelu/orig-img", ["IMG_0004.HEIC", "IMG_E0004.HEIC"])
    write_files(album / "ios-nelu/orig-vid", ["IMG_0005.MOV", "IMG_E0005.MOV"])
    write_files(album / "ios-nelu/edit-vid", ["IMG_0006.MOV"])


class TestRunFixIosMiscategorized:
    def test_mv_sums_every_source(self, tmp_path: Path) -> None:
        _two_sources_with_miscategorized_files(tmp_path)

        result = run_fix_ios(tmp_path, dry_run=False, mv_miscategorized=True)

        assert result.miscategorized_result is not None
        assert result.miscategorized_result.action == MiscategorizedAction.MV
        assert result.miscategorized_result.heic_from_orig == 2
        assert result.miscategorized_result.heic_from_rendered == 1
        assert result.miscategorized_result.mov_from_orig == 1
        assert result.miscategorized_result.mov_from_rendered == 1
        assert file_names(tmp_path / "ios-main/edit-img") == {
            "IMG_E0001.HEIC",
            "IMG_E0002.HEIC",
        }
        assert file_names(tmp_path / "ios-nelu/orig-vid") == {
            "IMG_0005.MOV",
            "IMG_0006.MOV",
        }
        assert format_fix_ios_result(result) == [
            (
                "Done. Moved 5 miscategorized file(s): 2 edited file(s) from orig-img, "
                "1 original file(s) from edit-img, 1 edited file(s) from orig-vid, "
                "1 original file(s) from edit-vid."
            ),
        ]

    def test_rm_dry_run_reports_without_deleting(self, tmp_path: Path) -> None:
        _two_sources_with_miscategorized_files(tmp_path)

        result = run_fix_ios(tmp_path, dry_run=True, rm_miscategorized=True)

        assert format_fix_ios_result(result, dry_run=True) == [
            (
                "[dry-run] Would remove 5 miscategorized file(s): "
                "2 edited file(s) from orig-img, 1 original file(s) from edit-img, "
                "1 edited file(s) from orig-vid, 1 original file(s) from edit-vid."
            ),
        ]
        assert "IMG_E0004.HEIC" in file_names(tmp_path / "ios-nelu/orig-img")

    def test_rm_safe_counts_only_files_already_in_place(self, tmp_path: Path) -> None:
        _two_sources_with_miscategorized_files(tmp_path)
        write_files(tmp_path / "ios-nelu/edit-img", ["IMG_E0004.HEIC"])

        result = run_fix_ios(tmp_path, dry_run=False, rm_miscategorized_safe=True)

        assert result.miscategorized_result is not None
        assert result.miscategorized_result.action == MiscategorizedAction.RM_SAFE
        assert result.miscategorized_result.heic_from_orig == 1
        assert format_fix_ios_result(result) == [
            "Done. Removed 1 miscategorized file(s): 1 edited file(s) from orig-img.",
        ]
        assert file_names(tmp_path / "ios-nelu/orig-img") == {"IMG_0004.HEIC"}
        assert "IMG_E0001.HEIC" in file_names(tmp_path / "ios-main/orig-img")
