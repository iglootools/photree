from collections.abc import Callable
from pathlib import Path

import pytest

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
from photree.foundation.gallery_metadata import (
    GALLERY_YAML,
    load_gallery_metadata,
)
from photree.foundation.layout import PHOTREE_DIR, SHARE_SENTINEL
from tests.fakes import invoke_cli
from tests.testkit import make_gallery, write_file


def _setup_album(gallery: Path, name: str) -> Path:
    album_dir = gallery / "albums" / name[:4] / name
    write_file(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    write_file(album_dir / "main-jpg" / "IMG_0001.jpg")
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    return album_dir


def _dangling_collection(gallery: Path) -> Path:
    col_dir = gallery / "collections" / "2024" / "2024-07 - Summer"
    col_dir.mkdir(parents=True)
    save_collection_metadata(
        col_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
            albums=[generate_album_id()],
        ),
    )
    return col_dir


class TestGalleryCheckPhases:
    def test_collections_are_checked_when_there_are_no_albums(
        self,
        tmp_path: Path,
    ) -> None:
        """Regression: "no albums" exited 0 before the collection phase ran."""
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _dangling_collection(gallery)

        result = invoke_cli(["gallery", "check", "-g", str(gallery)])

        assert result.exit_code == 1
        assert "Collections:" in result.output
        assert "not found in gallery" in result.output
        assert "Face clusters:" in result.output


class TestFaceClusterThreshold:
    @pytest.mark.parametrize("value", ["-0.1", "1.5"])
    def test_metadata_set_rejects_out_of_range(
        self,
        tmp_path: Path,
        value: str,
    ) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)

        result = invoke_cli(
            [
                "gallery",
                "metadata",
                "set",
                "-g",
                str(gallery),
                "--face-cluster-threshold",
                value,
            ],
        )

        assert result.exit_code == 2
        meta = load_gallery_metadata(gallery / PHOTREE_DIR / GALLERY_YAML)
        assert meta.face_cluster_threshold is None

    def test_metadata_set_accepts_zero(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)

        result = invoke_cli(
            [
                "gallery",
                "metadata",
                "set",
                "-g",
                str(gallery),
                "--face-cluster-threshold",
                "0.0",
            ],
        )

        assert result.exit_code == 0
        meta = load_gallery_metadata(gallery / PHOTREE_DIR / GALLERY_YAML)
        assert meta.face_cluster_threshold == 0.0

    def test_cluster_faces_rejects_out_of_range(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)

        result = invoke_cli(
            ["gallery", "cluster-faces", "-g", str(gallery), "--threshold", "2"],
        )

        assert result.exit_code == 2
        assert not (gallery / PHOTREE_DIR / "faces").exists()


class TestExport:
    def test_exports_gallery_albums_by_default(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        """Regression: --gallery-dir was ignored and the cwd was scanned."""
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _setup_album(gallery, "2024-07-14 - Hiking")
        share = tmp_path / "share"
        share.mkdir()
        (share / SHARE_SENTINEL).touch()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        chdir(elsewhere)

        result = invoke_cli(
            [
                "gallery",
                "export",
                "--gallery-dir",
                str(gallery),
                "--share-dir",
                str(share),
            ],
        )

        assert result.exit_code == 0, result.output
        assert (share / "2024-07-14 - Hiking").is_dir()

    def test_gallery_dir_and_dir_are_exclusive(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)

        result = invoke_cli(
            ["gallery", "export", "-g", str(gallery), "--dir", str(tmp_path)],
        )

        assert result.exit_code == 2


class TestListCollections:
    def test_paths_are_relative_to_cwd(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)
        col_dir = _dangling_collection(gallery)
        chdir(tmp_path)

        result = invoke_cli(
            ["gallery", "list-collections", "-g", str(gallery), "--format", "csv"],
        )

        assert result.exit_code == 0
        assert str(col_dir.relative_to(tmp_path)) in result.output

    def test_rejects_unknown_format(self, tmp_path: Path) -> None:
        gallery = make_gallery(tmp_path, faces_enabled=False)

        result = invoke_cli(
            ["gallery", "list-collections", "-g", str(gallery), "--format", "json"],
        )

        assert result.exit_code == 2


class TestGalleryAlbumDiscovery:
    def test_album_outside_the_albums_dir_is_not_listed(self, tmp_path: Path) -> None:
        """Regression: some gallery commands scanned the whole gallery root."""
        gallery = make_gallery(tmp_path, faces_enabled=False)
        _setup_album(gallery, "2024-07-14 - Trip")
        stray = gallery / "inbox" / "2024-08-01 - Stray"
        write_file(stray / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        save_album_metadata(stray, AlbumMetadata(id=generate_album_id()))

        result = invoke_cli(
            ["gallery", "list-albums", "-g", str(gallery), "--format", "csv"],
        )

        assert result.exit_code == 0
        assert "2024-07-14 - Trip" in result.output
        assert "Stray" not in result.output
