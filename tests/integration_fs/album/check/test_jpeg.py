from pathlib import Path

from photree.album.check.jpeg import check_jpeg_dir
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


class TestCheckJpegDir:
    def test_correct_jpeg_passes(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = check_jpeg_dir(
            album / MAIN_MEDIA_SOURCE.img_dir,
            album / MAIN_MEDIA_SOURCE.jpg_dir,
        )
        assert result.success
        assert len(result.present) == 2

    def test_missing_jpeg_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.jpg").unlink()

        result = check_jpeg_dir(
            album / MAIN_MEDIA_SOURCE.img_dir,
            album / MAIN_MEDIA_SOURCE.jpg_dir,
        )
        assert not result.success
        assert "IMG_E0001.jpg" in result.missing

    def test_extra_jpeg_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        write_file(album / MAIN_MEDIA_SOURCE.jpg_dir / "EXTRA.jpg", "extra")

        result = check_jpeg_dir(
            album / MAIN_MEDIA_SOURCE.img_dir,
            album / MAIN_MEDIA_SOURCE.jpg_dir,
        )
        assert not result.success
        assert "EXTRA.jpg" in result.extra
