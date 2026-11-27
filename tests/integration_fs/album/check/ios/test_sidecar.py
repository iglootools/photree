from pathlib import Path

from photree.album.check.ios.sidecar import (
    SidecarIssue,
    SidecarIssueKind,
    check_sidecars,
)
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from tests.testkit import write_file


def _setup_ios_album(album: Path) -> None:
    """Create a well-formed iOS album with matching files across all dirs."""
    # ios/orig-img: IMG_0001.HEIC + AAE, IMG_0002.PNG (no AAE for PNG)
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC", "heic-orig")
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.AAE", "aae-orig")
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG", "png-orig")

    write_file(
        album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC",
        "heic-rendered",
    )
    write_file(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_O0001.AAE", "aae-rendered")

    # main-img: rendered for 0001, orig PNG for 0002
    write_file(album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC", "heic-rendered")
    write_file(album / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.PNG", "png-orig")

    write_file(album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV", "mov-orig")
    write_file(album / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0003.MOV", "mov-orig")

    (album / MAIN_MEDIA_SOURCE.edit_vid_dir).mkdir(parents=True, exist_ok=True)

    write_file(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.jpg", "jpeg-converted")
    write_file(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0002.PNG", "png-copied")


class TestCheckSidecars:
    def test_correct_sidecars(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = check_sidecars(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
        )
        assert result.missing_sidecars == ()
        assert result.orphan_sidecars == ()

    def test_missing_aae_for_heic(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.AAE").unlink()

        result = check_sidecars(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
        )
        assert result.missing_sidecars == (
            SidecarIssue("IMG_0001.HEIC", "orig-img", SidecarIssueKind.MISSING_SIDECAR),
        )

    def test_missing_o_aae_for_rendered(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_O0001.AAE").unlink()

        result = check_sidecars(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
        )
        assert result.missing_sidecars == (
            SidecarIssue(
                "IMG_E0001.HEIC",
                "edit-img",
                SidecarIssueKind.MISSING_EDIT_SIDECAR,
            ),
        )

    def test_orphan_aae_in_orig(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC").unlink()

        result = check_sidecars(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
        )
        assert result.orphan_sidecars == (
            SidecarIssue("IMG_0001.AAE", "orig-img", SidecarIssueKind.ORPHAN_SIDECAR),
        )

    def test_orphan_o_aae_in_rendered(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC").unlink()

        result = check_sidecars(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
        )
        assert result.orphan_sidecars == (
            SidecarIssue(
                "IMG_O0001.AAE",
                "edit-img",
                SidecarIssueKind.ORPHAN_EDIT_SIDECAR,
            ),
        )
