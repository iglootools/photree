"""The ``album``, ``albums`` and ``gallery export`` commands, end to end."""

from collections.abc import Callable
from pathlib import Path

import pytest

from photree.album.id import generate_album_id
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from photree.foundation.layout import ALBUMS_DIR, SHARE_SENTINEL
from tests.fakes import fake_runtime, invoke_cli
from tests.testkit import write_file


def _album(path: Path) -> Path:
    """Create an iOS album with one photo and one video, browsable as JPEG."""
    write_file(path / MAIN_MEDIA_SOURCE.orig_img_dir / "IMG_0001.HEIC")
    write_file(path / MAIN_MEDIA_SOURCE.jpg_dir / "IMG_0001.jpg")
    write_file(path / MAIN_MEDIA_SOURCE.orig_vid_dir / "IMG_0002.MOV")
    write_file(path / MAIN_MEDIA_SOURCE.vid_dir / "IMG_0002.MOV")
    return path


def _share(tmp_path: Path) -> Path:
    share = tmp_path / "share"
    write_file(share / SHARE_SENTINEL, "")
    return share


class TestAlbumExport:
    def test_exports_the_album_and_reports_the_count(self, tmp_path: Path) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        share = _share(tmp_path)

        result = invoke_cli(
            ["album", "export", "--album-dir", str(album), "--share-dir", str(share)],
            runtime=fake_runtime(),
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
            result = invoke_cli(
                [
                    "album",
                    "export",
                    "--album-dir",
                    str(album),
                    "--share-dir",
                    str(share),
                ],
                runtime=fake_runtime(),
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

        result = invoke_cli(
            ["albums", "export", "--dir", str(albums), "--share-dir", str(share)],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert "Done. 2 album(s) exported, 0 failed." in result.output
        assert (share / "2024-07-14 - Trip" / MAIN_MEDIA_SOURCE.jpg_dir).is_dir()
        assert (share / "2024-08-01 - Hike" / MAIN_MEDIA_SOURCE.jpg_dir).is_dir()

    def test_invalid_config_exits_2(self, tmp_path: Path) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        share = _share(tmp_path)
        config = tmp_path / "config.toml"
        write_file(config, "[exporter\n")

        result = invoke_cli(
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
            runtime=fake_runtime(),
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

        result = invoke_cli(
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
            runtime=fake_runtime(),
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

        result = invoke_cli(
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
            runtime=fake_runtime(),
        )

        assert result.exit_code == 1, result.output
        assert "Done. 1 album(s) exported, 1 failed." in result.output
        assert "Failed albums:" in result.output
        undated = gallery / ALBUMS_DIR / "Undated"
        investigate = f'photree album export --album-dir "{undated}"'
        assert investigate in result.output


class TestDryRun:
    def test_album_export_names_the_target_and_writes_nothing(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        share = _share(tmp_path)
        chdir(tmp_path)

        result = invoke_cli(
            [
                "album",
                "export",
                "--album-dir",
                str(album),
                "--share-dir",
                str(share),
                "--share-layout",
                "albums",
                "--album-layout",
                "all",
                "--dry-run",
            ],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert (
            "[dry-run] Would export 2024-07-14 - Trip (ios) to"
            " share/2024/2024-07-14 - Trip: "
        ) in result.output
        assert sorted(p.name for p in share.iterdir()) == [SHARE_SENTINEL]

    @pytest.mark.parametrize("command", ["albums", "gallery"])
    def test_batch_export_summarizes_and_writes_nothing(
        self,
        tmp_path: Path,
        command: str,
    ) -> None:
        albums = tmp_path / "albums"
        for name in ("2024-07-14 - Trip", "2024-08-01 - Hike"):
            _album(albums / name)
        share = _share(tmp_path)

        result = invoke_cli(
            [command, "export", "--dir", str(albums), "--share-dir", str(share), "-n"],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert "[dry-run] 2 album(s) would be exported, 0 failed." in result.output
        assert sorted(p.name for p in share.iterdir()) == [SHARE_SENTINEL]


class TestSettingsErrorExitCodes:
    """Settings wrong whatever is on disk exit 2; a missing sentinel exits 1."""

    @pytest.mark.parametrize("command", ["album", "albums", "gallery"])
    def test_missing_share_dir_exits_2(self, tmp_path: Path, command: str) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")

        result = invoke_cli(
            [command, "export", "--album-dir", str(album)],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 2, result.output
        assert "No --share-dir specified" in result.output

    def test_albums_share_layout_without_all_exits_2(self, tmp_path: Path) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        share = _share(tmp_path)

        result = invoke_cli(
            [
                "album",
                "export",
                "--album-dir",
                str(album),
                "--share-dir",
                str(share),
                "--share-layout",
                "albums",
                "--album-layout",
                "browsable",
            ],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 2, result.output
        assert sorted(p.name for p in share.iterdir()) == [SHARE_SENTINEL]

    def test_unknown_profile_exits_2(self, tmp_path: Path) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        config = tmp_path / "config.toml"
        write_file(config, "")

        result = invoke_cli(
            [
                "albums",
                "export",
                "--album-dir",
                str(album),
                "--profile",
                "nosuch",
                "--config",
                str(config),
            ],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 2, result.output
        assert 'Unknown profile "nosuch"' in result.output

    def test_share_dir_without_sentinel_exits_1(self, tmp_path: Path) -> None:
        album = _album(tmp_path / "2024-07-14 - Trip")
        share = tmp_path / "share"
        share.mkdir()

        result = invoke_cli(
            ["gallery", "export", "--album-dir", str(album), "--share-dir", str(share)],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 1, result.output
        assert "sentinel file" in result.output
