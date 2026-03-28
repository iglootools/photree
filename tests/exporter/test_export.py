"""Tests for the album export logic."""

from pathlib import Path

import pytest

from photree.exporter.export import (
    compute_target_dir,
    export_album,
)
from photree.fsprotocol import (
    MAIN_MEDIA_SOURCE,
    PHOTREE_DIR,
    AlbumShareLayout,
    LinkMode,
    ShareDirectoryLayout,
    parse_album_year,
)


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


def _setup_ios_album(album_dir: Path) -> Path:
    """Create a typical iOS album with orig, rendered, combined dirs."""
    _setup_dir(
        album_dir / MAIN_MEDIA_SOURCE.orig_img_dir, ["IMG_0001.HEIC", "IMG_0002.HEIC"]
    )
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.edit_img_dir, ["IMG_E0001.HEIC"])
    _setup_dir(
        album_dir / MAIN_MEDIA_SOURCE.img_dir, ["IMG_E0001.HEIC", "IMG_0002.HEIC"]
    )
    _setup_dir(
        album_dir / MAIN_MEDIA_SOURCE.jpg_dir, ["IMG_E0001.JPEG", "IMG_0002.JPEG"]
    )
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.orig_vid_dir, ["IMG_0010.MOV"])
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.edit_vid_dir, ["IMG_E0010.MOV"])
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.vid_dir, ["IMG_E0010.MOV"])
    return album_dir


class TestParseAlbumYear:
    def test_standard_format(self) -> None:
        assert parse_album_year("2024-06-15 - Summer Vacation") == "2024"

    def test_date_only(self) -> None:
        assert parse_album_year("2024-06-15") == "2024"

    def test_date_with_underscore_suffix(self) -> None:
        assert parse_album_year("2024-01-01_New_Year") == "2024"

    def test_various_years(self) -> None:
        assert parse_album_year("2020-12-25 - Christmas") == "2020"
        assert parse_album_year("1999-01-01 - Millenium") == "1999"

    def test_no_date_prefix_raises(self) -> None:
        with pytest.raises(ValueError, match="does not start with YYYY-MM-DD"):
            parse_album_year("vacation-photos")

    def test_partial_date_raises(self) -> None:
        with pytest.raises(ValueError, match="does not start with YYYY-MM-DD"):
            parse_album_year("2024-06")


class TestComputeTargetDir:
    def test_flat_layout(self) -> None:
        result = compute_target_dir(
            Path("/share"), "my-album", ShareDirectoryLayout.FLAT
        )
        assert result == Path("/share/my-album")

    def test_albums_layout(self) -> None:
        result = compute_target_dir(
            Path("/share"), "2024-06-15 - Vacation", ShareDirectoryLayout.ALBUMS
        )
        assert result == Path("/share/2024/2024-06-15 - Vacation")

    def test_albums_layout_various_years(self) -> None:
        assert compute_target_dir(
            Path("/share"), "2020-12-25 - Christmas", ShareDirectoryLayout.ALBUMS
        ) == Path("/share/2020/2020-12-25 - Christmas")

    def test_albums_layout_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_target_dir(Path("/share"), "no-date", ShareDirectoryLayout.ALBUMS)


class TestExportOtherAlbum:
    def test_copies_all_files(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "my-album"
        _setup_dir(album_dir, ["photo1.jpg", "photo2.jpg", "video.mov"])
        target = tmp_path / "share" / "my-album"

        result = export_album(album_dir, target)

        assert result.album_name == "my-album"
        assert result.album_type == "other"
        assert result.files_copied == 3
        assert (target / "photo1.jpg").exists()
        assert (target / "photo2.jpg").exists()
        assert (target / "video.mov").exists()

    def test_copies_nested_directories(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "vacation"
        _setup_dir(album_dir / "sub", ["nested.jpg"])
        _setup_dir(album_dir, ["top.jpg"])
        target = tmp_path / "share" / "vacation"

        result = export_album(album_dir, target)

        assert (target / "top.jpg").exists()
        assert (target / "sub" / "nested.jpg").exists()
        assert result.files_copied == 2

    def test_skips_dotfiles(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "my-album"
        _setup_dir(album_dir, ["photo.jpg"])
        (album_dir / ".hidden").write_text("secret")
        (album_dir / ".photree").mkdir()
        (album_dir / ".photree" / "title.bkp").write_text("backup")
        target = tmp_path / "share" / "my-album"

        result = export_album(album_dir, target)

        assert (target / "photo.jpg").exists()
        assert not (target / ".hidden").exists()
        assert not (target / ".photree").exists()
        assert result.files_copied == 1


class TestExportIosMainJpg:
    def test_exports_jpg_and_vid_only(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        target = tmp_path / "share" / "trip"

        result = export_album(album_dir, target, album_layout=AlbumShareLayout.MAIN_JPG)

        assert result.album_type == "ios"
        # main-jpg/ and main-vid/ exported
        assert (target / "main-jpg" / "IMG_E0001.JPEG").exists()
        assert (target / "main-jpg" / "IMG_0002.JPEG").exists()
        assert (target / "main-vid" / "IMG_E0010.MOV").exists()
        # main-img/ should NOT be exported
        assert not (target / "main-img").exists()
        # archival dirs should NOT be exported
        assert not (target / MAIN_MEDIA_SOURCE.orig_img_dir).exists()
        assert not (target / MAIN_MEDIA_SOURCE.edit_img_dir).exists()
        assert result.files_copied == 3

    def test_is_the_default_layout(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        target = tmp_path / "share" / "trip"

        result = export_album(album_dir, target)

        assert (target / "main-jpg").exists()
        assert (target / "main-vid").exists()
        assert not (target / "main-img").exists()
        assert result.files_copied == 3


class TestExportIosMain:
    def test_strips_combined_prefix(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        target = tmp_path / "share" / "trip"

        result = export_album(album_dir, target, album_layout=AlbumShareLayout.MAIN)

        assert result.album_type == "ios"
        # main-img/ -> img/
        assert (target / "main-img" / "IMG_E0001.HEIC").exists()
        assert (target / "main-img" / "IMG_0002.HEIC").exists()
        # main-jpg/ -> jpg/
        assert (target / "main-jpg" / "IMG_E0001.JPEG").exists()
        # main-vid/ -> vid/
        assert (target / "main-vid" / "IMG_E0010.MOV").exists()
        # orig and rendered should NOT be exported
        assert not (target / MAIN_MEDIA_SOURCE.orig_img_dir).exists()
        assert not (target / MAIN_MEDIA_SOURCE.edit_img_dir).exists()
        assert not (target / MAIN_MEDIA_SOURCE.orig_vid_dir).exists()
        assert not (target / MAIN_MEDIA_SOURCE.edit_vid_dir).exists()

    def test_handles_missing_combined_dirs(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "minimal"
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.orig_img_dir, ["IMG_0001.HEIC"])
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.img_dir, ["IMG_0001.HEIC"])
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.jpg_dir, ["IMG_0001.JPEG"])
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.orig_vid_dir, ["IMG_0010.MOV"])
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.vid_dir, ["IMG_0010.MOV"])
        target = tmp_path / "share" / "minimal"

        result = export_album(album_dir, target, album_layout=AlbumShareLayout.MAIN)

        assert (target / "main-img" / "IMG_0001.HEIC").exists()
        assert (target / "main-jpg" / "IMG_0001.JPEG").exists()
        assert (target / "main-vid" / "IMG_0010.MOV").exists()
        assert result.files_copied == 3


class TestExportIosAll:
    def test_copies_orig_rendered_jpeg_and_recreates_combined(
        self, tmp_path: Path
    ) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        target = tmp_path / "share" / "trip"

        result = export_album(
            album_dir,
            target,
            album_layout=AlbumShareLayout.ALL,
            link_mode=LinkMode.COPY,
        )

        # orig dirs copied
        assert (target / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC").exists()
        assert (target / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.HEIC").exists()
        assert (target / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0010.MOV").exists()
        # rendered dirs copied
        assert (target / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC").exists()
        assert (target / MAIN_MEDIA_SOURCE.edit_vid_dir / "IMG_E0010.MOV").exists()
        # main-jpg copied
        assert (target / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_E0001.JPEG").exists()
        # main-img recreated (rendered preferred over orig)
        assert (target / MAIN_MEDIA_SOURCE.img_dir / "IMG_E0001.HEIC").exists()
        assert (target / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.HEIC").exists()
        # main-vid recreated
        assert (target / MAIN_MEDIA_SOURCE.vid_dir / "IMG_E0010.MOV").exists()
        assert result.files_copied > 0

    def test_combined_uses_hardlinks_by_default(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        target = tmp_path / "share" / "trip"

        export_album(album_dir, target, album_layout=AlbumShareLayout.ALL)

        # main-img files should be hardlinks to orig/rendered
        combined_file = target / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.HEIC"
        orig_file = target / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.HEIC"
        assert combined_file.stat().st_ino == orig_file.stat().st_ino

    def test_does_not_export_unmanaged(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        # Add an unmanaged file
        (album_dir / "notes.txt").write_text("my notes")
        (album_dir / "extra-dir").mkdir()
        (album_dir / "extra-dir" / "file.txt").write_text("extra")
        target = tmp_path / "share" / "trip"

        export_album(album_dir, target, album_layout=AlbumShareLayout.ALL)

        assert not (target / "notes.txt").exists()
        assert not (target / "extra-dir").exists()

    def test_creates_empty_photree_dir(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        (album_dir / PHOTREE_DIR).mkdir()
        (album_dir / PHOTREE_DIR / "title.bkp").write_text("backup")
        target = tmp_path / "share" / "trip"

        export_album(album_dir, target, album_layout=AlbumShareLayout.ALL)

        assert (target / PHOTREE_DIR).is_dir()
        assert not list((target / PHOTREE_DIR).iterdir())
