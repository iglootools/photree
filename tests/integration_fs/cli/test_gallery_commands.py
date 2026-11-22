from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app
from photree.collection.id import generate_collection_id
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
)
from photree.foundation.gallery_metadata import (
    GALLERY_YAML,
    GalleryMetadata,
    load_gallery_metadata,
    save_gallery_metadata,
)
from photree.foundation.layout import PHOTREE_DIR, SHARE_SENTINEL
from photree.gallery.cmd_handler.importer import (
    AlbumImportFailure,
    BatchImportResult,
)
from photree.gallery.output import format_import_all_summary, import_all_failed
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


def _setup_album(gallery: Path, name: str) -> Path:
    album_dir = gallery / "albums" / name[:4] / name
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0001.HEIC")
    _write(album_dir / "main-jpg" / "IMG_0001.jpg")
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
        gallery = _setup_gallery(tmp_path)
        _dangling_collection(gallery)

        result = runner.invoke(
            app,
            ["gallery", "check", "-g", str(gallery)],
            obj=ALL_DEPS_RUNTIME,
        )

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
        gallery = _setup_gallery(tmp_path)

        result = runner.invoke(
            app,
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
        gallery = _setup_gallery(tmp_path)

        result = runner.invoke(
            app,
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
        gallery = _setup_gallery(tmp_path)

        result = runner.invoke(
            app,
            ["gallery", "cluster-faces", "-g", str(gallery), "--threshold", "2"],
            obj=ALL_DEPS_RUNTIME,
        )

        assert result.exit_code == 2
        assert not (gallery / PHOTREE_DIR / "faces").exists()


class TestImportAllOutcome:
    """How the import and post-import check outcomes drive import-all's exit."""

    def test_post_import_check_failure_fails_the_run(self, tmp_path: Path) -> None:
        """Regression: post-import check failures did not affect the exit code."""
        source = tmp_path / "incoming" / "2024-07-14 - Hiking"
        target = tmp_path / "gallery" / "albums" / "2024" / source.name
        result = BatchImportResult(imported=(source,))

        assert import_all_failed(result, [target])
        assert format_import_all_summary(result, [target], 0) == (
            "Done. 1 album(s) imported, 0 failed, 1 failed post-import check."
        )

    def test_import_failure_fails_the_run(self, tmp_path: Path) -> None:
        source = tmp_path / "incoming" / "2024-07-14 - Hiking"
        result = BatchImportResult(
            failures=(AlbumImportFailure(source, OSError("disk full")),),
        )

        assert import_all_failed(result, [])
        assert format_import_all_summary(result, [], 0) == (
            "Done. 0 album(s) imported, 1 failed."
        )

    def test_clean_run_succeeds_and_counts_skips(self, tmp_path: Path) -> None:
        result = BatchImportResult(imported=(tmp_path / "2024-07-14 - Hiking",))

        assert not import_all_failed(result, [])
        assert format_import_all_summary(result, [], 2) == (
            "Done. 1 album(s) imported, 0 failed, 2 skipped."
        )


class TestExport:
    def test_exports_gallery_albums_by_default(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        """Regression: --gallery-dir was ignored and the cwd was scanned."""
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Hiking")
        share = tmp_path / "share"
        share.mkdir()
        (share / SHARE_SENTINEL).touch()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        chdir(elsewhere)

        result = runner.invoke(
            app,
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
        gallery = _setup_gallery(tmp_path)

        result = runner.invoke(
            app,
            ["gallery", "export", "-g", str(gallery), "--dir", str(tmp_path)],
        )

        assert result.exit_code == 2


class TestListCollections:
    def test_paths_are_relative_to_cwd(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir = _dangling_collection(gallery)
        chdir(tmp_path)

        result = runner.invoke(
            app,
            ["gallery", "list-collections", "-g", str(gallery), "--format", "csv"],
        )

        assert result.exit_code == 0
        assert str(col_dir.relative_to(tmp_path)) in result.output

    def test_rejects_unknown_format(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)

        result = runner.invoke(
            app,
            ["gallery", "list-collections", "-g", str(gallery), "--format", "json"],
        )

        assert result.exit_code == 2
