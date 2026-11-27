import os
from pathlib import Path

from photree.album.check.browsable import WrongSource, check_browsable_dir
from photree.album.formats import IMG_EXTENSIONS
from photree.album.store.media_source import MAIN_MEDIA_SOURCE, ios_img_number
from photree.foundation.linking import LinkMode
from tests.testkit import add_consistent_ios_album, write_file


def _setup_hardlinked_album(album: Path) -> None:
    """Create an iOS album where browsable files are hardlinks to orig/rendered."""
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC", "heic-orig")
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.AAE", "aae-orig")
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG", "png-orig")
    write_file(
        album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC",
        "heic-rendered",
    )
    write_file(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_O0001.AAE", "aae-rendered")

    (album / MAIN_MEDIA_SOURCE.img_dir).mkdir(parents=True, exist_ok=True)
    os.link(
        album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC",
        album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC",
    )
    os.link(
        album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG",
        album / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.PNG",
    )

    write_file(album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV", "mov-orig")
    (album / MAIN_MEDIA_SOURCE.edit_vid_dir).mkdir(parents=True, exist_ok=True)
    (album / MAIN_MEDIA_SOURCE.vid_dir).mkdir(parents=True, exist_ok=True)
    os.link(
        album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV",
        album / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0003.MOV",
    )

    write_file(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.jpg", "jpeg-converted")
    write_file(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0002.PNG", "png-copied")


def _setup_symlinked_album(album: Path) -> None:
    """Create an iOS album where browsable files are relative symlinks."""
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC", "heic-orig")
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.AAE", "aae-orig")
    write_file(album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG", "png-orig")
    write_file(
        album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC",
        "heic-rendered",
    )
    write_file(album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_O0001.AAE", "aae-rendered")

    (album / MAIN_MEDIA_SOURCE.img_dir).mkdir(parents=True, exist_ok=True)
    Path(album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").symlink_to(
        os.path.relpath(
            album / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC",
            album / MAIN_MEDIA_SOURCE.img_dir,
        ),
    )
    Path(album / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.PNG").symlink_to(
        os.path.relpath(
            album / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.PNG",
            album / MAIN_MEDIA_SOURCE.img_dir,
        ),
    )

    write_file(album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV", "mov-orig")
    (album / MAIN_MEDIA_SOURCE.edit_vid_dir).mkdir(parents=True, exist_ok=True)
    (album / MAIN_MEDIA_SOURCE.vid_dir).mkdir(parents=True, exist_ok=True)
    Path(album / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0003.MOV").symlink_to(
        os.path.relpath(
            album / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0003.MOV",
            album / MAIN_MEDIA_SOURCE.vid_dir,
        ),
    )

    write_file(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.jpg", "jpeg-converted")
    write_file(album / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0002.PNG", "png-copied")


class TestCheckBrowsableDir:
    def test_correct_album_passes(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_consistent_ios_album(album)

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
        add_consistent_ios_album(album)
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
        add_consistent_ios_album(album)
        write_file(album / MAIN_MEDIA_SOURCE.img_dir / "EXTRA.HEIC", "extra")

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
        add_consistent_ios_album(album)
        # Replace rendered with original in browsable (wrong)
        (album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").unlink()
        write_file(album / MAIN_MEDIA_SOURCE.img_dir / "IMG_0001.HEIC", "heic-orig")

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
        )
        assert not result.success
        assert result.wrong_source == (
            WrongSource(filename="IMG_0001.HEIC", expected="IMG_E0001.HEIC"),
        )

    def test_size_mismatch_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_consistent_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").write_text(
            "corrupted-different-size!!",
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
        add_consistent_ios_album(album)
        # Same length as the source's "heic-rendered", so only the checksum can
        # catch the change; a different length would be reported as a size mismatch.
        (album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").write_text(
            "heic-RENDERED",
        )

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
        assert result.size_mismatches == ()
        assert len(result.checksum_mismatches) == 1

    def test_same_size_change_passes_without_checksum(self, tmp_path: Path) -> None:
        """
        Pass a same-size change when the checksum is off.

        The size check alone cannot see a same-length change; that is what
        ``checksum=True`` pays for.
        """
        album = tmp_path / "album"
        add_consistent_ios_album(album)
        (album / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").write_text(
            "heic-RENDERED",
        )

        result = check_browsable_dir(
            album / MAIN_MEDIA_SOURCE.orig_img_dir,
            album / MAIN_MEDIA_SOURCE.edit_img_dir,
            album / MAIN_MEDIA_SOURCE.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
            checksum=False,
        )
        assert result.success


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
