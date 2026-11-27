from pathlib import Path

from photree.album.check.jpeg import check_jpeg_dir
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from tests.testkit import add_consistent_ios_album, write_file


class TestCheckJpegDir:
    def test_correct_jpeg_passes(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_consistent_ios_album(album)

        result = check_jpeg_dir(
            album / MAIN_MEDIA_SOURCE.img_dir,
            album / MAIN_MEDIA_SOURCE.jpg_dir,
        )
        assert result.success
        assert len(result.present) == 2

    def test_missing_jpeg_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_consistent_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.jpg").unlink()

        result = check_jpeg_dir(
            album / MAIN_MEDIA_SOURCE.img_dir,
            album / MAIN_MEDIA_SOURCE.jpg_dir,
        )
        assert not result.success
        assert "IMG_E0001.jpg" in result.missing

    def test_extra_jpeg_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_consistent_ios_album(album)
        write_file(album / MAIN_MEDIA_SOURCE.jpg_dir / "EXTRA.jpg", "extra")

        result = check_jpeg_dir(
            album / MAIN_MEDIA_SOURCE.img_dir,
            album / MAIN_MEDIA_SOURCE.jpg_dir,
        )
        assert not result.success
        assert "EXTRA.jpg" in result.extra
