"""Tests for album refresh CLI command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_album(album_dir: Path) -> None:
    album_dir.mkdir(parents=True, exist_ok=True)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0411.HEIC")
    _write(album_dir / "ios-main" / "orig-vid" / "IMG_0115.MOV")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


class TestAlbumRefresh:
    def test_creates_media_ids(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_album(album)

        result = runner.invoke(app, ["album", "refresh", "-a", str(album)])

        assert result.exit_code == 0
        assert "Media IDs:" in result.output
        assert load_media_metadata(album) is not None

    def test_reports_counts(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_album(album)

        result = runner.invoke(app, ["album", "refresh", "-a", str(album)])

        assert "2 new image(s)" in result.output
        assert "1 new video(s)" in result.output

    def test_dry_run(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_album(album)

        result = runner.invoke(app, ["album", "refresh", "-a", str(album), "--dry-run"])

        assert result.exit_code == 0
        assert "Media IDs:" in result.output
        assert load_media_metadata(album) is None

    def test_idempotent(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_album(album)

        runner.invoke(app, ["album", "refresh", "-a", str(album)])
        result = runner.invoke(app, ["album", "refresh", "-a", str(album)])

        assert result.exit_code == 0
        assert "no changes" in result.output
