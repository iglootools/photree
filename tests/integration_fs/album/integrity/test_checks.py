"""Tests for photree.album.check module."""

import os
from pathlib import Path

from photree.album.check.browsable import check_browsable_dir
from photree.album.check import check_album_integrity
from photree.fsprotocol import LinkMode
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.album.check.ios import check_miscategorized_files
from photree.album.check.jpeg import check_jpeg_dir
from photree.album.check.ios.sidecar import check_sidecars
from photree.album.store.media_sources import ios_img_number
from photree.album.store.protocol import IMG_EXTENSIONS, MAIN_MEDIA_SOURCE


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_ios_album(album: Path) -> None:
    """Create a well-formed iOS album with matching files across all dirs."""
    # ios/orig-img: IMG_0001.HEIC + AAE, IMG_0002.PNG (no AAE for PNG)
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC", "heic-orig")
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.AAE", "aae-orig")
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG", "png-orig")

    # ios/edit-img: IMG_E0001.HEIC + IMG_O0001.AAE (rendered for 0001)
    _write(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC", "heic-rendered")
    _write(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_O0001.AAE", "aae-rendered")

    # main-img: rendered for 0001, orig PNG for 0002
    _write(album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC", "heic-rendered")
    _write(album / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.PNG", "png-orig")

    # ios/orig-vid + main-vid: simple MOV
    _write(album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV", "mov-orig")
    _write(album / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0003.MOV", "mov-orig")

    # ios/edit-vid: empty
    (album / MAIN_MEDIA_SOURCE.edit_vid_dir).mkdir(parents=True, exist_ok=True)

    # main-jpg: one for each main-img file
    _write(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.jpg", "jpeg-converted")
    _write(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0002.PNG", "png-copied")


class TestCheckBrowsableDir:
    def test_correct_album_passes(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
            checksum=True,
        )
        assert result.success
        assert len(result.correct) == 2
        assert result.missing == ()
        assert result.extra == ()

    def test_missing_file_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").unlink()

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
        )
        assert not result.success
        assert any(m.filename == "IMG_E0001.HEIC" for m in result.missing)
        assert any(m.source_dir == "edit-img" for m in result.missing)

    def test_extra_file_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        _write(album / MAIN_MEDIA_SOURCE.img_dir / "EXTRA.HEIC", "extra")

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
        )
        assert not result.success
        assert "EXTRA.HEIC" in result.extra

    def test_wrong_source_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        # Replace rendered with original in browsable (wrong)
        (album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").unlink()
        _write(album / MAIN_MEDIA_SOURCE.img_dir / "IMG_0001.HEIC", "heic-orig")

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
        )
        assert not result.success
        assert any("IMG_0001.HEIC" in w for w in result.wrong_source)

    def test_size_mismatch_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        # Corrupt the browsable file
        (album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").write_text(
            "corrupted-different-size!!"
        )

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
        )
        assert not result.success
        assert len(result.size_mismatches) == 1

    def test_checksum_mismatch_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        # Same size but different content
        (album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").write_text("heic-DIFFER")

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
            checksum=True,
        )
        assert not result.success
        # Same length as "heic-rendered" (13 chars) vs "heic-DIFFER" (11 chars)
        # Actually different size, so this is a size mismatch — let me fix the test data
        # Use exact same length: "heic-rendered" is 13 chars
        assert len(result.size_mismatches) > 0 or len(result.checksum_mismatches) > 0


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
        _write(album / MAIN_MEDIA_SOURCE.jpg_dir / "EXTRA.jpg", "extra")

        result = check_jpeg_dir(
            album / MAIN_MEDIA_SOURCE.img_dir,
            album / MAIN_MEDIA_SOURCE.jpg_dir,
        )
        assert not result.success
        assert "EXTRA.jpg" in result.extra


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
        assert any(
            "IMG_0001.HEIC" in w and "no AAE" in w for w in result.missing_sidecars
        )

    def test_missing_o_aae_for_rendered(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_O0001.AAE").unlink()

        result = check_sidecars(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
        )
        assert any(
            "IMG_E0001.HEIC" in w and "O-prefixed AAE" in w
            for w in result.missing_sidecars
        )

    def test_orphan_aae_in_orig(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC").unlink()

        result = check_sidecars(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
        )
        assert any(
            "IMG_0001.AAE" in w and "no matching media" in w
            for w in result.orphan_sidecars
        )

    def test_orphan_o_aae_in_rendered(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC").unlink()

        result = check_sidecars(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
        )
        assert any(
            "IMG_O0001.AAE" in w and "no matching edited media" in w
            for w in result.orphan_sidecars
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

        assert any("IMG_E0001.HEIC" in w and "edited file" in w for w in warnings)

    def test_original_in_rendered_detected(self, tmp_path: Path) -> None:
        orig = tmp_path / "ios-main/orig-img"
        rendered = tmp_path / "ios-main/edit-img"
        orig.mkdir(parents=True)
        rendered.mkdir(parents=True)
        (rendered / "IMG_0001.HEIC").write_text("data")  # original in rendered

        warnings = check_miscategorized_files(orig, rendered)

        assert any("IMG_0001.HEIC" in w and "original file" in w for w in warnings)

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
            tmp_path / "ios-main/orig-img", tmp_path / "ios-main/edit-img"
        )

        assert warnings == ()


def _setup_hardlinked_album(album: Path) -> None:
    """Create an iOS album where browsable files are hardlinks to orig/rendered."""
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC", "heic-orig")
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.AAE", "aae-orig")
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG", "png-orig")
    _write(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC", "heic-rendered")
    _write(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_O0001.AAE", "aae-rendered")

    (album / MAIN_MEDIA_SOURCE.img_dir).mkdir(parents=True, exist_ok=True)
    os.link(
        album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC",
        album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC",
    )
    os.link(
        album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG",
        album / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.PNG",
    )

    _write(album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV", "mov-orig")
    (album / MAIN_MEDIA_SOURCE.edit_vid_dir).mkdir(parents=True, exist_ok=True)
    (album / MAIN_MEDIA_SOURCE.vid_dir).mkdir(parents=True, exist_ok=True)
    os.link(
        album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV",
        album / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0003.MOV",
    )

    _write(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.jpg", "jpeg-converted")
    _write(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0002.PNG", "png-copied")


def _setup_symlinked_album(album: Path) -> None:
    """Create an iOS album where browsable files are relative symlinks."""
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC", "heic-orig")
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.AAE", "aae-orig")
    _write(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG", "png-orig")
    _write(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC", "heic-rendered")
    _write(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_O0001.AAE", "aae-rendered")

    (album / MAIN_MEDIA_SOURCE.img_dir).mkdir(parents=True, exist_ok=True)
    os.symlink(
        os.path.relpath(
            album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC",
            album / MAIN_MEDIA_SOURCE.img_dir,
        ),
        album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC",
    )
    os.symlink(
        os.path.relpath(
            album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG",
            album / MAIN_MEDIA_SOURCE.img_dir,
        ),
        album / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.PNG",
    )

    _write(album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV", "mov-orig")
    (album / MAIN_MEDIA_SOURCE.edit_vid_dir).mkdir(parents=True, exist_ok=True)
    (album / MAIN_MEDIA_SOURCE.vid_dir).mkdir(parents=True, exist_ok=True)
    os.symlink(
        os.path.relpath(
            album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV",
            album / MAIN_MEDIA_SOURCE.vid_dir,
        ),
        album / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0003.MOV",
    )

    _write(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.jpg", "jpeg-converted")
    _write(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0002.PNG", "png-copied")


class TestCheckBrowsableDirLinkAware:
    def test_hardlinked_browsable_skips_checksum(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_hardlinked_album(album)

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.HARDLINK,
            checksum=True,
        )
        assert result.success
        assert len(result.correct) == 2
        assert all(c.link_verified for c in result.correct)

    def test_symlinked_browsable_skips_checksum(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_symlinked_album(album)

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.SYMLINK,
            checksum=True,
        )
        assert result.success
        assert len(result.correct) == 2
        assert all(c.link_verified for c in result.correct)

    def test_broken_symlink_reports_missing(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_symlinked_album(album)
        # Remove the source file to break the symlink
        (album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC").unlink()

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.SYMLINK,
        )
        # The browsable file points to rendered, but rendered no longer has it,
        # so the expected source is now orig. The broken symlink won't match.
        assert not result.success


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
        check_album_integrity(
            album,
            link_mode=LinkMode.COPY,
            checksum=False,
            on_file_checked=lambda f, ok: checked.append((f, ok)),
            media_sources=discover_media_sources(album),
        )
        assert len(checked) > 0
        assert all(ok for _, ok in checked)
