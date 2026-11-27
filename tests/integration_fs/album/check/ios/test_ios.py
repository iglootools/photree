from pathlib import Path

from photree.album.check.ios import (
    MiscategorizedFile,
    MiscategorizedKind,
    check_miscategorized_files,
)


class TestCheckMiscategorizedFiles:
    def test_rendered_in_orig_detected(self, tmp_path: Path) -> None:
        orig = tmp_path / "ios-main/orig-img"
        rendered = tmp_path / "ios-main/edit-img"
        orig.mkdir(parents=True)
        rendered.mkdir(parents=True)
        (orig / "IMG_0001.HEIC").write_text("data")
        (orig / "IMG_E0001.HEIC").write_text("data")  # rendered in orig

        warnings = check_miscategorized_files(orig, rendered)

        assert warnings == (
            MiscategorizedFile(
                "IMG_E0001.HEIC",
                "orig-img",
                MiscategorizedKind.EDITED_IN_ORIG,
            ),
        )

    def test_original_in_rendered_detected(self, tmp_path: Path) -> None:
        orig = tmp_path / "ios-main/orig-img"
        rendered = tmp_path / "ios-main/edit-img"
        orig.mkdir(parents=True)
        rendered.mkdir(parents=True)
        (rendered / "IMG_0001.HEIC").write_text("data")  # original in rendered

        warnings = check_miscategorized_files(orig, rendered)

        assert warnings == (
            MiscategorizedFile(
                "IMG_0001.HEIC",
                "edit-img",
                MiscategorizedKind.ORIGINAL_IN_EDIT,
            ),
        )

    def test_no_warnings_when_correct(self, tmp_path: Path) -> None:
        orig = tmp_path / "ios-main/orig-img"
        rendered = tmp_path / "ios-main/edit-img"
        orig.mkdir(parents=True)
        rendered.mkdir(parents=True)
        (orig / "IMG_0001.HEIC").write_text("data")
        (orig / "IMG_0001.AAE").write_text("data")
        (rendered / "IMG_E0001.HEIC").write_text("data")
        (rendered / "IMG_O0001.AAE").write_text("data")

        warnings = check_miscategorized_files(orig, rendered)

        assert warnings == ()

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        warnings = check_miscategorized_files(
            tmp_path / "ios-main/orig-img",
            tmp_path / "ios-main/edit-img",
        )

        assert warnings == ()
