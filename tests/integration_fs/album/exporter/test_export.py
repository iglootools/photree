"""Tests for the album export logic."""

from pathlib import Path

import pytest

from photree.album.exporter.single import (
    compute_target_dir,
    export_album,
)
from photree.fsprotocol import AlbumShareLayout, ShareDirectoryLayout
from photree.album.store.protocol import (
    MAIN_MEDIA_SOURCE,
    parse_album_month,
    parse_album_year,
    std_media_source,
)
from photree.fsprotocol import LinkMode, PHOTREE_DIR


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


def _setup_ios_album(album_dir: Path) -> Path:
    """Create a typical iOS album with orig, rendered, browsable dirs."""
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


class TestParseAlbumMonth:
    def test_standard_format(self) -> None:
        assert parse_album_month("2024-06-15 - Summer Vacation") == "2024-06"

    def test_date_only(self) -> None:
        assert parse_album_month("2024-06-15") == "2024-06"

    def test_month_precision(self) -> None:
        assert parse_album_month("2024-06 - Summer") == "2024-06"

    def test_range_uses_start_month(self) -> None:
        assert parse_album_month("2024-06-15--2024-07-17 - Trip") == "2024-06"

    def test_no_date_prefix_raises(self) -> None:
        with pytest.raises(ValueError, match="does not start with YYYY-MM"):
            parse_album_month("vacation-photos")

    def test_year_only_raises(self) -> None:
        with pytest.raises(ValueError, match="does not start with YYYY-MM"):
            parse_album_month("2024 - Family")


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

    def test_by_month_layout(self) -> None:
        result = compute_target_dir(
            Path("/share"), "2024-06-15 - Vacation", ShareDirectoryLayout.BY_MONTH
        )
        assert result == Path("/share/2024-06/2024-06-15 - Vacation")

    def test_by_month_layout_range_uses_start_month(self) -> None:
        assert compute_target_dir(
            Path("/share"),
            "2024-06-15--2024-07-17 - Trip",
            ShareDirectoryLayout.BY_MONTH,
        ) == Path("/share/2024-06/2024-06-15--2024-07-17 - Trip")

    def test_by_month_layout_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_target_dir(Path("/share"), "no-date", ShareDirectoryLayout.BY_MONTH)


class TestExportOtherAlbum:
    def test_copies_all_files(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "my-album"
        _setup_dir(album_dir, ["photo1.jpg", "photo2.jpg", "video.mov"])
        target = tmp_path / "share" / "my-album"

        result = export_album(album_dir, target)

        assert result.album_name == "my-album"
        assert result.album_type == "std"
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

        result = export_album(
            album_dir, target, album_layout=AlbumShareLayout.BROWSABLE_JPG
        )

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
    def test_strips_browsable_prefix(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        target = tmp_path / "share" / "trip"

        result = export_album(
            album_dir, target, album_layout=AlbumShareLayout.BROWSABLE
        )

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

    def test_handles_missing_browsable_dirs(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "minimal"
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.orig_img_dir, ["IMG_0001.HEIC"])
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.img_dir, ["IMG_0001.HEIC"])
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.jpg_dir, ["IMG_0001.JPEG"])
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.orig_vid_dir, ["IMG_0010.MOV"])
        _setup_dir(album_dir / MAIN_MEDIA_SOURCE.vid_dir, ["IMG_0010.MOV"])
        target = tmp_path / "share" / "minimal"

        result = export_album(
            album_dir, target, album_layout=AlbumShareLayout.BROWSABLE
        )

        assert (target / "main-img" / "IMG_0001.HEIC").exists()
        assert (target / "main-jpg" / "IMG_0001.JPEG").exists()
        assert (target / "main-vid" / "IMG_0010.MOV").exists()
        assert result.files_copied == 3


class TestExportIosAll:
    def test_copies_orig_rendered_jpeg_and_recreates_browsable(
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

    def test_browsable_uses_hardlinks_by_default(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        target = tmp_path / "share" / "trip"

        export_album(album_dir, target, album_layout=AlbumShareLayout.ALL)

        # main-img files should be hardlinks to orig/rendered
        browsable_file = target / MAIN_MEDIA_SOURCE.img_dir / "IMG_0002.HEIC"
        orig_file = target / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.HEIC"
        assert browsable_file.stat().st_ino == orig_file.stat().st_ino

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


def _setup_photree_metadata(album_dir: Path) -> None:
    """Create representative .photree metadata + a derived cache dir."""
    photree = album_dir / PHOTREE_DIR
    (photree).mkdir(parents=True, exist_ok=True)
    (photree / "album.yaml").write_text("id: 0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1\n")
    _setup_dir(photree / "media-ids", ["main.yaml"])
    # cache/ is derived and must be excluded from the archive layout.
    _setup_dir(photree / "cache" / "exif", ["main.yaml"])
    _setup_dir(photree / "cache" / "faces", ["main.npz"])


class TestExportIosArchive:
    def test_copies_only_archive_and_metadata(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        _setup_photree_metadata(album_dir)
        target = tmp_path / "share" / "trip"

        result = export_album(album_dir, target, album_layout=AlbumShareLayout.ARCHIVE)

        assert result.album_type == "ios"
        # archive (orig + edit) copied
        assert (target / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC").exists()
        assert (target / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0002.HEIC").exists()
        assert (target / MAIN_MEDIA_SOURCE.edit_img_dir / "IMG_E0001.HEIC").exists()
        assert (target / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0010.MOV").exists()
        assert (target / MAIN_MEDIA_SOURCE.edit_vid_dir / "IMG_E0010.MOV").exists()
        # derived browsable/JPEG dirs dropped
        assert not (target / MAIN_MEDIA_SOURCE.img_dir).exists()
        assert not (target / MAIN_MEDIA_SOURCE.jpg_dir).exists()
        assert not (target / MAIN_MEDIA_SOURCE.vid_dir).exists()

    def test_copies_photree_metadata_excluding_cache(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "trip")
        _setup_photree_metadata(album_dir)
        target = tmp_path / "share" / "trip"

        export_album(album_dir, target, album_layout=AlbumShareLayout.ARCHIVE)

        assert (target / PHOTREE_DIR / "album.yaml").exists()
        assert (target / PHOTREE_DIR / "media-ids" / "main.yaml").exists()
        # derived cache must NOT be copied
        assert not (target / PHOTREE_DIR / "cache").exists()


def _setup_std_source(album_dir: Path, name: str = "dana") -> None:
    """Create a std media source with a real std-{name}/ archive."""
    ms = std_media_source(name)
    _setup_dir(album_dir / ms.orig_img_dir, ["photo1.heic", "photo2.heic"])
    _setup_dir(album_dir / ms.edit_img_dir, ["photo1.heic"])
    _setup_dir(album_dir / ms.orig_vid_dir, ["clip.mov"])
    _setup_dir(album_dir / ms.img_dir, ["photo1.heic", "photo2.heic"])
    _setup_dir(album_dir / ms.jpg_dir, ["photo1.jpg", "photo2.jpg"])


class TestExportStdArchive:
    def test_copies_std_archive_and_drops_derived(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "std-album"
        _setup_std_source(album_dir)
        _setup_photree_metadata(album_dir)
        target = tmp_path / "share" / "std-album"

        result = export_album(album_dir, target, album_layout=AlbumShareLayout.ARCHIVE)

        assert result.album_type == "std"
        # archive (orig + edit) copied
        assert (target / "std-dana" / "orig-img" / "photo1.heic").exists()
        assert (target / "std-dana" / "edit-img" / "photo1.heic").exists()
        assert (target / "std-dana" / "orig-vid" / "clip.mov").exists()
        # derived browsable/JPEG dirs dropped
        assert not (target / "dana-img").exists()
        assert not (target / "dana-jpg").exists()
        assert (target / PHOTREE_DIR / "album.yaml").exists()

    def test_mixed_ios_and_std_sources(self, tmp_path: Path) -> None:
        album_dir = _setup_ios_album(tmp_path / "mixed")
        _setup_std_source(album_dir)
        target = tmp_path / "share" / "mixed"

        export_album(album_dir, target, album_layout=AlbumShareLayout.ARCHIVE)

        # iOS archive preserved, iOS browsable dropped
        assert (target / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC").exists()
        assert not (target / MAIN_MEDIA_SOURCE.jpg_dir).exists()
        # std archive preserved, std browsable dropped
        assert (target / "std-dana" / "orig-img" / "photo1.heic").exists()
        assert not (target / "dana-jpg").exists()


class TestExportPlainArchive:
    def test_plain_dir_falls_back_to_full_copy(self, tmp_path: Path) -> None:
        album_dir = tmp_path / "loose"
        _setup_dir(album_dir, ["a.jpg", "b.jpg"])
        target = tmp_path / "share" / "loose"

        result = export_album(album_dir, target, album_layout=AlbumShareLayout.ARCHIVE)

        assert (target / "a.jpg").exists()
        assert (target / "b.jpg").exists()
        assert result.files_copied == 2
