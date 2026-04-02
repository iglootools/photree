"""Tests for album init and albums init CLI commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from photree.cli import app
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import (
    ALBUM_YAML,
    AlbumMetadata,
    generate_album_id,
)
from photree.fsprotocol import PHOTREE_DIR

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_media_source(album_dir: Path) -> None:
    """Create a minimal iOS media source so the album is detected."""
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


def _mark_album(album_dir: Path) -> None:
    """Create .photree/album.yaml with a generated ID."""
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))


# ---------------------------------------------------------------------------
# album init
# ---------------------------------------------------------------------------


class TestAlbumInit:
    def test_creates_album_yaml(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        result = runner.invoke(app, ["album", "init", "-a", str(album)])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "Album ID:" in result.output
        assert load_album_metadata(album) is not None

    def test_generates_valid_id(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        runner.invoke(app, ["album", "init", "-a", str(album)])
        metadata = load_album_metadata(album)
        assert metadata is not None
        assert metadata.id  # non-empty

    def test_fails_if_already_initialized(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        _mark_album(album)
        result = runner.invoke(app, ["album", "init", "-a", str(album)])
        assert result.exit_code == 1
        assert "already initialized" in result.output

    def test_does_not_overwrite_existing_id(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        original_id = generate_album_id()
        save_album_metadata(album, AlbumMetadata(id=original_id))
        runner.invoke(app, ["album", "init", "-a", str(album)])
        metadata = load_album_metadata(album)
        assert metadata is not None
        assert metadata.id == original_id

    def test_creates_photree_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        runner.invoke(app, ["album", "init", "-a", str(album)])
        assert (album / PHOTREE_DIR / ALBUM_YAML).is_file()


# ---------------------------------------------------------------------------
# albums init
# ---------------------------------------------------------------------------


class TestAlbumsInit:
    def test_initializes_multiple_albums(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        a2 = tmp_path / "2024-07-15 - Trip B"
        _setup_media_source(a1)
        _setup_media_source(a2)

        result = runner.invoke(app, ["albums", "init", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert load_album_metadata(a1) is not None
        assert load_album_metadata(a2) is not None

    def test_fails_if_any_already_initialized(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        a2 = tmp_path / "2024-07-15 - Trip B"
        _setup_media_source(a1)
        _setup_media_source(a2)
        _mark_album(a1)

        result = runner.invoke(app, ["albums", "init", "-d", str(tmp_path)])
        assert result.exit_code == 1
        assert "already initialized" in result.output

    def test_does_not_overwrite_existing_ids(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        _setup_media_source(a1)
        original_id = generate_album_id()
        save_album_metadata(a1, AlbumMetadata(id=original_id))

        runner.invoke(app, ["albums", "init", "-d", str(tmp_path)])
        metadata = load_album_metadata(a1)
        assert metadata is not None
        assert metadata.id == original_id

    def test_dry_run_does_not_create_files(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        _setup_media_source(a1)

        result = runner.invoke(
            app, ["albums", "init", "-d", str(tmp_path), "--dry-run"]
        )
        assert result.exit_code == 0
        assert load_album_metadata(a1) is None

    def test_explicit_album_dirs(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        a2 = tmp_path / "2024-07-15 - Trip B"
        a1.mkdir()
        a2.mkdir()

        result = runner.invoke(app, ["albums", "init", "-a", str(a1), "-a", str(a2)])
        assert result.exit_code == 0
        assert load_album_metadata(a1) is not None
        assert load_album_metadata(a2) is not None

    def test_discovers_albums_without_album_yaml(self, tmp_path: Path) -> None:
        """--dir mode should find directories with media sources even without album.yaml."""
        a1 = tmp_path / "2024-07-14 - Trip A"
        _setup_media_source(a1)
        # No _mark_album — album.yaml does not exist yet

        result = runner.invoke(app, ["albums", "init", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert load_album_metadata(a1) is not None

    def test_no_albums_found(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["albums", "init", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert "No albums found" in result.output

    def test_dir_and_album_dir_mutually_exclusive(self, tmp_path: Path) -> None:
        a1 = tmp_path / "album"
        a1.mkdir()
        result = runner.invoke(
            app, ["albums", "init", "-d", str(tmp_path), "-a", str(a1)]
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.output
