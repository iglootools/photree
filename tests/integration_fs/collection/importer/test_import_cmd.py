"""Tests for ``photree collection import`` CLI command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from photree.album.id import format_album_external_id, generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app
from photree.collection.id import generate_collection_id
from photree.collection.importer.selection import SELECTION_CSV, SELECTION_DIR
from photree.collection.store.metadata import (
    load_collection_metadata,
    save_collection_metadata,
)
from photree.collection.store.protocol import (
    CollectionKind,
    CollectionLifecycle,
    CollectionMetadata,
)
from photree.fsprotocol import GalleryMetadata, save_gallery_metadata

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_csv(path: Path, entries: list[str]) -> None:
    """Write a collection to-import.csv with header."""
    lines = ["entry,date", *[f"{e}," for e in entries]]
    path.write_text("\n".join(lines) + "\n")


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata())
    return gallery


def _setup_album(gallery: Path, name: str) -> tuple[Path, str]:
    album_dir = gallery / "albums" / "2024" / name
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)
    aid = generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=aid))
    return album_dir, aid


def _setup_collection(tmp_path: Path) -> Path:
    col_dir = tmp_path / "my-collection"
    col_dir.mkdir()
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            kind=CollectionKind.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        ),
    )
    return col_dir


class TestCollectionImportCmd:
    def test_import_from_csv(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")
        col_dir = _setup_collection(tmp_path)

        ext_id = format_album_external_id(album_id)
        _write_csv(col_dir / SELECTION_CSV, [ext_id])

        result = runner.invoke(
            app,
            [
                "collection",
                "import",
                "-c",
                str(col_dir),
                "-g",
                str(gallery),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Import complete" in result.output

        loaded = load_collection_metadata(col_dir)
        assert loaded is not None
        assert album_id in loaded.albums

        # CSV should be deleted
        assert not (col_dir / SELECTION_CSV).exists()

    def test_import_from_dir(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")
        col_dir = _setup_collection(tmp_path)

        sel_dir = col_dir / SELECTION_DIR
        sel_dir.mkdir()
        (sel_dir / "2024-07-14 - Trip").write_text("")

        result = runner.invoke(
            app,
            [
                "collection",
                "import",
                "-c",
                str(col_dir),
                "-g",
                str(gallery),
            ],
        )
        assert result.exit_code == 0, result.output
        loaded = load_collection_metadata(col_dir)
        assert loaded is not None
        assert album_id in loaded.albums
        # Selection dir should be cleaned up
        assert not sel_dir.exists()

    def test_import_fails_on_unresolved(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir = _setup_collection(tmp_path)

        _write_csv(col_dir / SELECTION_CSV, ["nonexistent-album"])

        result = runner.invoke(
            app,
            [
                "collection",
                "import",
                "-c",
                str(col_dir),
                "-g",
                str(gallery),
            ],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_dry_run_no_changes(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id = _setup_album(gallery, "2024-07-14 - Trip")
        col_dir = _setup_collection(tmp_path)

        ext_id = format_album_external_id(album_id)
        _write_csv(col_dir / SELECTION_CSV, [ext_id])

        result = runner.invoke(
            app,
            [
                "collection",
                "import",
                "-c",
                str(col_dir),
                "-g",
                str(gallery),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output

        loaded = load_collection_metadata(col_dir)
        assert loaded is not None
        assert loaded.albums == []
        # CSV should NOT be deleted
        assert (col_dir / SELECTION_CSV).exists()

    def test_import_merges_with_existing(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _, album_id1 = _setup_album(gallery, "2024-07-14 - Trip A")
        _, album_id2 = _setup_album(gallery, "2024-07-15 - Trip B")
        col_dir = tmp_path / "my-collection"
        col_dir.mkdir()
        save_collection_metadata(
            col_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                kind=CollectionKind.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                albums=[album_id1],
            ),
        )

        ext_id2 = format_album_external_id(album_id2)
        _write_csv(col_dir / SELECTION_CSV, [ext_id2])

        result = runner.invoke(
            app,
            [
                "collection",
                "import",
                "-c",
                str(col_dir),
                "-g",
                str(gallery),
            ],
        )
        assert result.exit_code == 0
        loaded = load_collection_metadata(col_dir)
        assert loaded is not None
        assert album_id1 in loaded.albums
        assert album_id2 in loaded.albums

    def test_fails_without_init(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir = tmp_path / "uninit"
        col_dir.mkdir()
        _write_csv(col_dir / SELECTION_CSV, ["something"])

        result = runner.invoke(
            app,
            [
                "collection",
                "import",
                "-c",
                str(col_dir),
                "-g",
                str(gallery),
            ],
        )
        assert result.exit_code == 1
        assert "No collection metadata" in result.output

    def test_fails_without_selection(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir = _setup_collection(tmp_path)

        result = runner.invoke(
            app,
            [
                "collection",
                "import",
                "-c",
                str(col_dir),
                "-g",
                str(gallery),
            ],
        )
        assert result.exit_code == 1
        assert "No selection entries" in result.output
