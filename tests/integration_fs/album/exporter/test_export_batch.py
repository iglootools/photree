"""Tests for the batch album export."""

from pathlib import Path

from photree.album.exporter.batch import (
    discover_albums,
    run_batch_export,
)
from photree.fs import (
    MAIN_MEDIA_SOURCE,
    AlbumShareLayout,
    LinkMode,
    ShareDirectoryLayout,
)


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


def _setup_ios_album(album_dir: Path) -> Path:
    """Create a minimal iOS album."""
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.orig_img_dir, ["IMG_0001.HEIC"])
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.img_dir, ["IMG_0001.HEIC"])
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.jpg_dir, ["IMG_0001.JPEG"])
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.orig_vid_dir, ["IMG_0010.MOV"])
    _setup_dir(album_dir / MAIN_MEDIA_SOURCE.vid_dir, ["IMG_0010.MOV"])
    return album_dir


class TestDiscoverAlbums:
    def test_discovers_ios_and_other_albums(self, tmp_path: Path) -> None:
        base = tmp_path / "albums"
        base.mkdir()
        _setup_ios_album(base / "ios-trip")
        _setup_dir(base / "other-trip", ["photo.jpg"])

        albums = discover_albums(base)

        names = [a.name for a in albums]
        assert "ios-trip" in names
        assert "other-trip" in names

    def test_empty_directory(self, tmp_path: Path) -> None:
        base = tmp_path / "albums"
        base.mkdir()

        assert discover_albums(base) == []


class TestBatchExport:
    def test_exports_multiple_albums(self, tmp_path: Path) -> None:
        base = tmp_path / "albums"
        base.mkdir()
        _setup_ios_album(base / "trip-paris")
        _setup_ios_album(base / "trip-london")
        share_dir = tmp_path / "share"
        share_dir.mkdir()

        result = run_batch_export(
            base_dir=base,
            share_dir=share_dir,
            album_layout=AlbumShareLayout.MAIN_JPG,
        )

        assert result.exported == 2
        assert len(result.failed) == 0
        assert (share_dir / "trip-paris" / "main-jpg" / "IMG_0001.JPEG").exists()
        assert (share_dir / "trip-london" / "main-jpg" / "IMG_0001.JPEG").exists()

    def test_exports_explicit_album_dirs(self, tmp_path: Path) -> None:
        album_a = _setup_ios_album(tmp_path / "trip-a")
        album_b = _setup_ios_album(tmp_path / "trip-b")
        share_dir = tmp_path / "share"
        share_dir.mkdir()

        result = run_batch_export(
            album_dirs=[album_a, album_b],
            share_dir=share_dir,
            album_layout=AlbumShareLayout.MAIN_JPG,
        )

        assert result.exported == 2
        assert (share_dir / "trip-a" / "main-jpg" / "IMG_0001.JPEG").exists()
        assert (share_dir / "trip-b" / "main-jpg" / "IMG_0001.JPEG").exists()

    def test_empty_base_dir(self, tmp_path: Path) -> None:
        base = tmp_path / "albums"
        base.mkdir()
        share_dir = tmp_path / "share"
        share_dir.mkdir()

        result = run_batch_export(base_dir=base, share_dir=share_dir)

        assert result.exported == 0
        assert len(result.failed) == 0

    def test_callbacks_are_invoked(self, tmp_path: Path) -> None:
        album = _setup_ios_album(tmp_path / "trip")
        share_dir = tmp_path / "share"
        share_dir.mkdir()

        exporting_names: list[str] = []
        exported_names: list[str] = []

        result = run_batch_export(
            album_dirs=[album],
            share_dir=share_dir,
            on_exporting=exporting_names.append,
            on_exported=exported_names.append,
        )

        assert result.exported == 1
        assert exporting_names == ["trip"]
        assert exported_names == ["trip"]

    def test_mixed_ios_and_other(self, tmp_path: Path) -> None:
        base = tmp_path / "albums"
        base.mkdir()
        _setup_ios_album(base / "ios-album")
        _setup_dir(base / "plain-album", ["photo.jpg"])
        share_dir = tmp_path / "share"
        share_dir.mkdir()

        result = run_batch_export(
            base_dir=base,
            share_dir=share_dir,
            album_layout=AlbumShareLayout.MAIN_JPG,
            link_mode=LinkMode.COPY,
        )

        assert result.exported == 2
        # iOS album uses main-jpg layout
        assert (share_dir / "ios-album" / "main-jpg" / "IMG_0001.JPEG").exists()
        # Other album copies everything
        assert (share_dir / "plain-album" / "photo.jpg").exists()

    def test_albums_share_layout(self, tmp_path: Path) -> None:
        album = _setup_ios_album(tmp_path / "2024-06-15 - Vacation")
        share_dir = tmp_path / "share"
        share_dir.mkdir()

        result = run_batch_export(
            album_dirs=[album],
            share_dir=share_dir,
            share_layout=ShareDirectoryLayout.ALBUMS,
            album_layout=AlbumShareLayout.ALL,
            link_mode=LinkMode.COPY,
        )

        assert result.exported == 1
        target = share_dir / "2024" / "2024-06-15 - Vacation"
        assert (target / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC").exists()

    def test_albums_share_layout_invalid_name_fails_gracefully(
        self, tmp_path: Path
    ) -> None:
        album = _setup_ios_album(tmp_path / "no-date-album")
        share_dir = tmp_path / "share"
        share_dir.mkdir()

        errors: list[tuple[str, str]] = []

        result = run_batch_export(
            album_dirs=[album],
            share_dir=share_dir,
            share_layout=ShareDirectoryLayout.ALBUMS,
            album_layout=AlbumShareLayout.ALL,
            link_mode=LinkMode.COPY,
            on_error=lambda name, msg: errors.append((name, msg)),
        )

        assert result.exported == 0
        assert len(result.failed) == 1
        assert "YYYY-MM-DD" in result.failed[0][1]
