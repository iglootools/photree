from pathlib import Path

from photree.album.check import check_album_integrity
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.foundation.linking import LinkMode
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


class TestCheckIosAlbumIntegrity:
    def test_correct_album_passes(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = check_album_integrity(
            album,
            link_mode=LinkMode.COPY,
            checksum=True,
            media_sources=discover_media_sources(album),
        )
        assert result.success

    def test_calls_on_file_checked(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        checked: list[tuple[str, bool]] = []

        def record_checked(name: str, *, success: bool) -> None:
            checked.append((name, success))

        check_album_integrity(
            album,
            link_mode=LinkMode.COPY,
            checksum=False,
            on_file_checked=record_checked,
            media_sources=discover_media_sources(album),
        )
        assert len(checked) > 0
        assert all(ok for _, ok in checked)
