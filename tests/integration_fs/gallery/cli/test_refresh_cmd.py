from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.collection.id import generate_collection_id
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
)
from photree.foundation.layout import BROWSABLE_DIR, PHOTREE_DIR
from tests.fakes import invoke_cli
from tests.testkit import make_gallery


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


def _setup_album(gallery: Path, name: str = "2024-07-14 - Trip") -> Path:
    """Create an album with an empty std source, which refresh converts nothing in."""
    album_dir = gallery / "albums" / name[:4] / name
    (album_dir / "std-cam" / "orig-img").mkdir(parents=True)
    (album_dir / "cam-jpg").mkdir()
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    return album_dir


def _refresh(gallery: Path, *args: str) -> tuple[int, str]:
    result = invoke_cli(["gallery", "refresh", "-g", str(gallery), *args])
    return result.exit_code, result.output


class TestGalleryRefreshWithoutAlbums:
    def test_collections_and_browsable_are_refreshed(self, tmp_path: Path) -> None:
        """Regression: "no albums" exited 0 before the gallery-level stages ran."""
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _setup_collection(gallery)

        exit_code, output = _refresh(gallery)

        assert exit_code == 0
        assert "No albums found." in output
        assert "Collections:" in output
        assert "✓ browsable (0 album(s), 1 collection(s), 0 symlink(s))" in output


class TestGalleryRefreshStages:
    def test_clean_gallery_renders_browsable(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _setup_album(gallery)

        exit_code, output = _refresh(gallery)

        assert exit_code == 0
        assert "Done. 1 album(s) refreshed, 0 failed." in output
        assert "✓ browsable (1 album(s), 0 collection(s), 1 symlink(s))" in output
        assert (
            gallery
            / BROWSABLE_DIR
            / "public"
            / "albums"
            / "by-year"
            / "2024"
            / "2024-07-14 - Trip"
            / "cam-jpg"
        ).is_symlink()

    def test_dry_run_renders_nothing(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _setup_album(gallery)

        exit_code, output = _refresh(gallery, "--dry-run")

        assert exit_code == 0
        assert "[dry-run] 1 album(s) would be refreshed, 0 failed." in output
        assert not (gallery / BROWSABLE_DIR).exists()

    def test_collection_error_fails_before_browsable(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _setup_album(gallery)
        broken = gallery / "collections" / "Broken"
        (broken / PHOTREE_DIR).mkdir(parents=True)
        (broken / PHOTREE_DIR / "collection.yaml").write_text("", encoding="utf-8")

        exit_code, output = _refresh(gallery)

        assert exit_code == 1
        assert "collection metadata cannot be read" in output
        assert "Browsable:" not in output
        assert not (gallery / BROWSABLE_DIR).exists()

    def test_browsable_error_fails_the_refresh(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _setup_album(gallery)
        stray = gallery / BROWSABLE_DIR / "notes.txt"
        stray.parent.mkdir()
        stray.write_text("keep me", encoding="utf-8")

        exit_code, output = _refresh(gallery)

        assert exit_code == 1
        assert "browsable/ contains a regular file" in output
        assert stray.read_text(encoding="utf-8") == "keep me"
