"""Tests for photree.album.optimize module."""

import os
from pathlib import Path

from photree.album.optimize import OptimizeResult, optimize_album
from photree.fsprotocol import (
    MAIN_IMG_DIR,
    MAIN_JPG_DIR,
    MAIN_VID_DIR,
    LinkMode,
    ORIG_IMG_DIR,
    ORIG_VID_DIR,
    EDIT_IMG_DIR,
    EDIT_VID_DIR,
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_ios_album(album: Path) -> None:
    """Create a well-formed iOS album with copies in combined dirs."""
    _write(album / ORIG_IMG_DIR / "IMG_0001.HEIC", "heic-orig")
    _write(album / ORIG_IMG_DIR / "IMG_0001.AAE", "aae-orig")
    _write(album / ORIG_IMG_DIR / "IMG_0002.PNG", "png-orig")
    _write(album / EDIT_IMG_DIR / "IMG_E0001.HEIC", "heic-rendered")
    _write(album / EDIT_IMG_DIR / "IMG_O0001.AAE", "aae-rendered")
    _write(album / MAIN_IMG_DIR / "IMG_E0001.HEIC", "heic-rendered")
    _write(album / MAIN_IMG_DIR / "IMG_0002.PNG", "png-orig")
    _write(album / ORIG_VID_DIR / "IMG_0003.MOV", "mov-orig")
    (album / EDIT_VID_DIR).mkdir(parents=True, exist_ok=True)
    _write(album / MAIN_VID_DIR / "IMG_0003.MOV", "mov-orig")
    _write(album / MAIN_JPG_DIR / "IMG_E0001.jpg", "jpeg-converted")
    _write(album / MAIN_JPG_DIR / "IMG_0002.PNG", "png-copied")


class TestOptimizeAlbum:
    def test_creates_hardlinks_by_default(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = optimize_album(album)

        assert result == OptimizeResult(
            heic_count=2, mov_count=1, link_mode=LinkMode.HARDLINK
        )
        # Verify hardlinks (same inode)
        assert (
            os.stat(album / MAIN_IMG_DIR / "IMG_E0001.HEIC").st_ino
            == os.stat(album / EDIT_IMG_DIR / "IMG_E0001.HEIC").st_ino
        )
        assert (
            os.stat(album / MAIN_IMG_DIR / "IMG_0002.PNG").st_ino
            == os.stat(album / ORIG_IMG_DIR / "IMG_0002.PNG").st_ino
        )
        assert (
            os.stat(album / MAIN_VID_DIR / "IMG_0003.MOV").st_ino
            == os.stat(album / ORIG_VID_DIR / "IMG_0003.MOV").st_ino
        )

    def test_creates_symlinks_when_requested(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = optimize_album(album, link_mode=LinkMode.SYMLINK)

        assert result.link_mode == LinkMode.SYMLINK
        heic_file = album / MAIN_IMG_DIR / "IMG_E0001.HEIC"
        assert heic_file.is_symlink()
        assert not os.path.isabs(os.readlink(heic_file))
        assert (
            heic_file.resolve() == (album / EDIT_IMG_DIR / "IMG_E0001.HEIC").resolve()
        )

    def test_skips_combined_jpeg(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        jpeg_before = (album / MAIN_JPG_DIR / "IMG_E0001.jpg").read_text()

        optimize_album(album)

        # main-jpg should be untouched (still a regular file, same content)
        jpeg_file = album / MAIN_JPG_DIR / "IMG_E0001.jpg"
        assert jpeg_file.read_text() == jpeg_before
        assert not jpeg_file.is_symlink()

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        heic_ino_before = os.stat(album / MAIN_IMG_DIR / "IMG_E0001.HEIC").st_ino

        result = optimize_album(album, dry_run=True)

        assert result.heic_count == 2
        assert result.mov_count == 1
        # Inode should be unchanged (file not replaced)
        assert (
            os.stat(album / MAIN_IMG_DIR / "IMG_E0001.HEIC").st_ino == heic_ino_before
        )

    def test_empty_album(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()

        result = optimize_album(album)

        assert result == OptimizeResult(
            heic_count=0, mov_count=0, link_mode=LinkMode.HARDLINK
        )
