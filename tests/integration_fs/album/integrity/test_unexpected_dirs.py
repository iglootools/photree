"""Tests for unexpected directory detection in albums."""

from pathlib import Path

from photree.album.check.unexpected_dirs import check_unexpected_dirs
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.album.store.protocol import (
    MAIN_MEDIA_SOURCE,
    SELECTION_DIR,
    std_media_source,
)


def _setup_ios_album(album: Path) -> None:
    """Create a well-formed iOS album directory structure (main source)."""
    (album / ".photree").mkdir(parents=True)
    (album / MAIN_MEDIA_SOURCE.orig_img_dir).mkdir(parents=True)
    (album / MAIN_MEDIA_SOURCE.edit_img_dir).mkdir(parents=True)
    (album / MAIN_MEDIA_SOURCE.orig_vid_dir).mkdir(parents=True)
    (album / MAIN_MEDIA_SOURCE.edit_vid_dir).mkdir(parents=True)
    (album / MAIN_MEDIA_SOURCE.img_dir).mkdir()
    (album / MAIN_MEDIA_SOURCE.vid_dir).mkdir()
    (album / MAIN_MEDIA_SOURCE.jpg_dir).mkdir()


def _setup_std_album(album: Path, name: str = "main") -> None:
    """Create a well-formed std album directory structure."""
    ms = std_media_source(name)
    (album / ".photree").mkdir(parents=True, exist_ok=True)
    (album / ms.orig_img_dir).mkdir(parents=True)
    (album / ms.orig_vid_dir).mkdir(parents=True)
    (album / ms.img_dir).mkdir(exist_ok=True)
    (album / ms.vid_dir).mkdir(exist_ok=True)
    (album / ms.jpg_dir).mkdir(exist_ok=True)


class TestCheckUnexpectedDirs:
    def test_no_unexpected_dirs_ios(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert result.success
        assert result.unexpected == ()

    def test_no_unexpected_dirs_std(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_std_album(album)

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert result.success
        assert result.unexpected == ()

    def test_unexpected_dir_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / "random-folder").mkdir()

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert not result.success
        assert result.unexpected == ("random-folder",)

    def test_multiple_unexpected_dirs_sorted(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / "zzz-extra").mkdir()
        (album / "aaa-stray").mkdir()

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert not result.success
        assert result.unexpected == ("aaa-stray", "zzz-extra")

    def test_selection_dir_not_flagged(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / SELECTION_DIR).mkdir()

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert result.success

    def test_dotdirs_ignored(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / ".hidden-dir").mkdir()

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert result.success

    def test_multi_media_source(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        _setup_std_album(album, name="bruno")

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert result.success

    def test_multi_media_source_with_unexpected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        _setup_std_album(album, name="bruno")
        (album / "leftover").mkdir()

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert not result.success
        assert result.unexpected == ("leftover",)

    def test_no_media_sources_only_expected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        (album / ".photree").mkdir(parents=True)
        (album / SELECTION_DIR).mkdir()

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert result.success

    def test_no_media_sources_unexpected_flagged(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        (album / ".photree").mkdir(parents=True)
        (album / "stray").mkdir()

        result = check_unexpected_dirs(
            album, media_sources=discover_media_sources(album)
        )
        assert not result.success
        assert result.unexpected == ("stray",)
