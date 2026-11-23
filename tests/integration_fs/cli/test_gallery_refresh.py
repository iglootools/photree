from pathlib import Path

from typer.testing import CliRunner

from photree.cli import app
from photree.collection.id import generate_collection_id
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
)
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from tests.fakes import ALL_DEPS_RUNTIME

runner = CliRunner()


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata(faces_enabled=False))
    return gallery


def _setup_collection(gallery: Path, name: str = "2024-07 - Summer") -> Path:
    col_dir = gallery / "collections" / "2024" / name
    col_dir.mkdir(parents=True)
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        ),
    )
    return col_dir


def _refresh(gallery: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(
        app,
        ["gallery", "refresh", "-g", str(gallery), *args],
        obj=ALL_DEPS_RUNTIME,
    )
    return result.exit_code, result.output


class TestGalleryRefreshWithoutAlbums:
    def test_collections_and_browsable_are_refreshed(self, tmp_path: Path) -> None:
        """Regression: "no albums" exited 0 before the gallery-level stages ran."""
        gallery = _setup_gallery(tmp_path)
        _setup_collection(gallery)

        exit_code, output = _refresh(gallery)

        assert exit_code == 0
        assert "No albums found." in output
        assert "Collections:" in output
        assert "✓ browsable (0 album(s), 1 collection(s), 0 symlink(s))" in output
