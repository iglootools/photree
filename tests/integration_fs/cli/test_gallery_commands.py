"""CLI tests for gallery commands: check phases, thresholds, export, listing."""

from __future__ import annotations

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
from photree.gallery.cli import import_all_cmd
from photree.gallery.cmd_handler.importer import (
    AlbumImportFailure,
    BatchImportResult,
)

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
        self, tmp_path: Path, stub_sips_on_path: Path
    ) -> None:
        """Regression: "no albums" exited 0 before the collection phase ran."""
        gallery = _setup_gallery(tmp_path)
        _dangling_collection(gallery)

        result = runner.invoke(app, ["gallery", "check", "-g", str(gallery)])

        assert result.exit_code == 1
        assert "Collections:" in result.output
        assert "not found in gallery" in result.output
        assert "Face clusters:" in result.output


class TestFaceClusterThreshold:
    @pytest.mark.parametrize("value", ["-0.1", "1.5"])
    def test_metadata_set_rejects_out_of_range(
        self, tmp_path: Path, value: str
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

        assert result.exit_code == 1
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

    def test_cluster_faces_rejects_out_of_range(
        self, tmp_path: Path, stub_sips_on_path: Path
    ) -> None:
        gallery = _setup_gallery(tmp_path)

        result = runner.invoke(
            app,
            ["gallery", "cluster-faces", "-g", str(gallery), "--threshold", "2"],
        )

        assert result.exit_code == 1
        assert not (gallery / PHOTREE_DIR / "faces").exists()


class TestImportAllExitCode:
    def test_post_import_check_failure_exits_1(
        self, tmp_path: Path, stub_sips_on_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: post-import check failures did not affect the exit code."""
        gallery = _setup_gallery(tmp_path)
        source = tmp_path / "incoming" / "2024-07-14 - Hiking"
        _write(source / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        target = gallery / "albums" / "2024" / source.name
        # Stand-ins for the real import/check, which need sips and the face
        # model: this test is about how their outcomes drive the exit code.
        monkeypatch.setattr(
            import_all_cmd,
            "run_batch_import",
            lambda *_a, **_k: BatchImportResult(imported=(source,)),
        )
        monkeypatch.setattr(
            import_all_cmd, "run_batch_post_import_check", lambda *_a: [target]
        )

        result = runner.invoke(
            app,
            ["gallery", "import-all", "-d", str(source.parent), "-g", str(gallery)],
        )

        assert result.exit_code == 1
        assert "1 album(s) imported, 0 failed, 1 failed post-import check" in (
            result.output
        )

    def test_import_failure_is_counted(
        self, tmp_path: Path, stub_sips_on_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        source = tmp_path / "incoming" / "2024-07-14 - Hiking"
        _write(source / "ios-main" / "orig-img" / "IMG_0001.HEIC")
        monkeypatch.setattr(
            import_all_cmd,
            "run_batch_import",
            lambda *_a, **_k: BatchImportResult(
                failures=(AlbumImportFailure(source, OSError("disk full")),)
            ),
        )

        result = runner.invoke(
            app,
            ["gallery", "import-all", "-d", str(source.parent), "-g", str(gallery)],
        )

        assert result.exit_code == 1
        assert "0 album(s) imported, 1 failed" in result.output


class TestExport:
    def test_exports_gallery_albums_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: --gallery-dir was ignored and the cwd was scanned."""
        gallery = _setup_gallery(tmp_path)
        _setup_album(gallery, "2024-07-14 - Hiking")
        share = tmp_path / "share"
        share.mkdir()
        (share / SHARE_SENTINEL).touch()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

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

        assert result.exit_code == 1


class TestListCollections:
    def test_paths_are_relative_to_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        col_dir = _dangling_collection(gallery)
        monkeypatch.chdir(tmp_path)

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
