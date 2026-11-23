"""The ``album``, ``albums`` and ``gallery export`` commands, end to end."""

from pathlib import Path

from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from photree.foundation.layout import ALBUMS_DIR, SHARE_SENTINEL
from tests.fakes import fake_runtime

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _album(path: Path) -> Path:
    """Create an iOS album with one photo and one video, browsable as JPEG."""
    _write(path / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC")
    _write(path / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0001.jpg")
    _write(path / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0002.MOV")
    _write(path / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0002.MOV")
    return path


def _share(tmp_path: Path) -> Path:
    share = tmp_path / "share"
    _write(share / SHARE_SENTINEL, "")
    return share


class TestAlbumExport:
    def test_exports_the_album_and_reports_the_count(self, tmp_path: Path) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        share = _share(tmp_path)

        result = runner.invoke(
            app,
            ["album", "export", "--album-dir", str(album), "--share-dir", str(share)],
            obj=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert "Done. Exported 2024-07-14 - Trip (ios): 2 file(s)." in result.output
        target = share / "2024-07-14 - Trip"
        assert (target / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0001.jpg").is_file()
        assert (target / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0002.MOV").is_file()
        assert not (target / MAIN_MEDIA_SOURCE.orig_img_dir).exists()

    def test_filesystem_error_is_reported_without_a_traceback(
        self,
        tmp_path: Path,
    ) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        share = _share(tmp_path)
        target = share / "2024-07-14 - Trip"
        target.mkdir()
        target.chmod(0o500)
        try:
            result = runner.invoke(
                app,
                [
                    "album",
                    "export",
                    "--album-dir",
                    str(album),
                    "--share-dir",
                    str(share),
                ],
                obj=fake_runtime(),
            )
        finally:
            target.chmod(0o700)

        assert result.exit_code == 1, result.output
        assert isinstance(result.exception, SystemExit)
        assert 'Could not export "' in result.output
        assert "Permission denied" in result.output
        assert "Check that the share is mounted, writable" in result.output


class TestAlbumsExport:
    def test_exports_every_album_under_dir(self, tmp_path: Path) -> None:
        albums = tmp_path / "albums"
        _album(albums / "2024-07-14 - Trip")
        _album(albums / "2024-08-01 - Hike")
        share = _share(tmp_path)

        result = runner.invoke(
            app,
            ["albums", "export", "--dir", str(albums), "--share-dir", str(share)],
            obj=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert "Done. 2 album(s) exported, 0 failed." in result.output
        assert (share / "2024-07-14 - Trip" / MAIN_MEDIA_SOURCE.jpg_dir).is_dir()
        assert (share / "2024-08-01 - Hike" / MAIN_MEDIA_SOURCE.jpg_dir).is_dir()

    def test_invalid_config_exits_2(self, tmp_path: Path) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        share = _share(tmp_path)
        config = tmp_path / "config.toml"
        _write(config, "[exporter\n")

        result = runner.invoke(
            app,
            [
                "albums",
                "export",
                "--album-dir",
                str(album),
                "--share-dir",
                str(share),
                "--config",
                str(config),
            ],
            obj=fake_runtime(),
        )

        assert result.exit_code == 2, result.output
        assert not (share / "2024-07-14 - Trip").exists()

    def test_failed_album_is_reported_with_an_investigate_command(
        self,
        tmp_path: Path,
    ) -> None:
        albums = tmp_path / "albums"
        _album(albums / "2024-07-14 - Trip")
        _album(albums / "Undated")
        share = _share(tmp_path)

        result = runner.invoke(
            app,
            [
                "albums",
                "export",
                "--dir",
                str(albums),
                "--share-dir",
                str(share),
                "--share-layout",
                "by-month",
            ],
            obj=fake_runtime(),
        )

        assert result.exit_code == 1, result.output
        assert "Done. 1 album(s) exported, 1 failed." in result.output
        assert "Failed albums:" in result.output
        investigate = f'photree album export --album-dir "{albums / "Undated"}"'
        assert investigate in result.output
        assert (share / "2024-07" / "2024-07-14 - Trip").is_dir()


class TestGalleryExport:
    def test_failed_album_is_reported_with_an_investigate_command(
        self,
        tmp_path: Path,
    ) -> None:
        gallery = tmp_path / "gallery"
        gallery.mkdir()
        save_gallery_metadata(gallery, GalleryMetadata(faces_enabled=False))
        for name in ("2024-07-14 - Trip", "Undated"):
            album = _album(gallery / ALBUMS_DIR / name)
            save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
        share = _share(tmp_path)

        result = runner.invoke(
            app,
            [
                "gallery",
                "export",
                "--gallery-dir",
                str(gallery),
                "--share-dir",
                str(share),
                "--share-layout",
                "by-month",
            ],
            obj=fake_runtime(),
        )

        assert result.exit_code == 1, result.output
        assert "Done. 1 album(s) exported, 1 failed." in result.output
        assert "Failed albums:" in result.output
        undated = gallery / ALBUMS_DIR / "Undated"
        investigate = f'photree album export --album-dir "{undated}"'
        assert investigate in result.output
