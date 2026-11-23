from pathlib import Path

import pytest
from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from tests.fakes import ALL_DEPS_RUNTIME

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata(faces_enabled=False))
    return gallery


def _setup_album(base_dir: Path, name: str) -> Path:
    """Create an album with one iOS picture and its browsable copy and JPEG."""
    album_dir = base_dir / name
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC", "x" * 2048)
    _write(album_dir / "main-img" / "IMG_0001.HEIC", "x" * 2048)
    _write(album_dir / "main-jpg" / "IMG_0001.jpg", "y" * 512)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    return album_dir


class TestAlbumStats:
    def test_album_stats_prints_the_tables(self, tmp_path: Path) -> None:
        album_dir = _setup_album(tmp_path, "2024-06-15 - Hiking")

        result = runner.invoke(
            app,
            ["album", "stats", "--album-dir", str(album_dir)],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 0, result.output
        assert "Overview" in result.output
        assert "By Media Source" in result.output
        assert "4.50 KiB" in result.output  # apparent size: 2048 + 2048 + 512

    def test_album_stats_exits_1_when_the_name_cannot_be_parsed(
        self,
        tmp_path: Path,
    ) -> None:
        album_dir = _setup_album(tmp_path, "not an album name")

        result = runner.invoke(
            app,
            ["album", "stats", "--album-dir", str(album_dir)],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 1
        assert 'Album name "not an album name" cannot be parsed.' in result.output


_CSV_LISTINGS = [
    ("list-albums", "No albums found.", "id,path,"),
    ("list-media", "No albums found.", "album_id,media_source,type,id,key"),
    ("list-collections", "No collections found.", "id,path,date,"),
]


class TestEmptyCsvListings:
    @pytest.mark.parametrize(("command", "notice", "header"), _CSV_LISTINGS)
    def test_empty_csv_still_has_its_header(
        self,
        tmp_path: Path,
        command: str,
        notice: str,
        header: str,
    ) -> None:
        gallery = _setup_gallery(tmp_path)

        result = runner.invoke(
            app,
            ["gallery", command, "--format", "csv", "--gallery-dir", str(gallery)],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 0, result.output
        # strip(): the album-list spinner leaves a blank line on stdout.
        assert result.stdout.strip().startswith(header)
        assert len(result.stdout.strip().splitlines()) == 1
        assert notice in result.stderr

    @pytest.mark.parametrize(("command", "notice", "header"), _CSV_LISTINGS)
    def test_empty_csv_output_file_is_written(
        self,
        tmp_path: Path,
        command: str,
        notice: str,
        header: str,
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        out = tmp_path / "out.csv"

        result = runner.invoke(
            app,
            [
                "gallery",
                command,
                "--format",
                "csv",
                "--gallery-dir",
                str(gallery),
                "--output",
                str(out),
            ],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 0, result.output
        assert out.read_text(encoding="utf-8").startswith(header)
        assert notice in result.stderr
