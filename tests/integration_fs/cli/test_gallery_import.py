"""CLI tests for ``gallery import`` / ``gallery import-all``.

These cover the fast control-flow paths (validation gate, skip, clobber,
dry-run) that exit before any real media conversion or face-model loading.
The import/reimport happy paths are covered at the function level in
``test_importer.py`` / ``test_reimport.py``.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.cli import app
from photree.fsprotocol import GalleryMetadata, LinkMode, save_gallery_metadata

runner = CliRunner()


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(
        gallery, GalleryMetadata(link_mode=LinkMode.HARDLINK, faces_enabled=False)
    )
    return gallery


def _make_source(base: Path, name: str, *, album_id: str | None = None) -> Path:
    d = base / name
    _write(d / "ios-main/orig-img/IMG_0001.HEIC")
    if album_id is not None:
        save_album_metadata(d, AlbumMetadata(id=album_id))
    return d


def _place_gallery_album(gallery: Path, name: str, *, album_id: str) -> Path:
    target = gallery / "albums" / name[:4] / name
    _write(target / "ios-main/orig-img/IMG_0001.HEIC")
    save_album_metadata(target, AlbumMetadata(id=album_id))
    return target


class TestValidationGate:
    def test_collision_aborts_batch(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Morning")
        _make_source(base, "2024-07-14 - Evening")

        result = runner.invoke(
            app, ["gallery", "import-all", "-d", str(base), "-g", str(gallery)]
        )

        assert result.exit_code == 1
        # Nothing was imported.
        assert not (gallery / "albums").exists()

    def test_bad_name_aborts(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        source = _make_source(tmp_path / "src", "not-an-album-name")

        result = runner.invoke(
            app, ["gallery", "import", "-a", str(source), "-g", str(gallery)]
        )

        assert result.exit_code == 1
        assert not (gallery / "albums").exists()


class TestSkip:
    def test_already_imported_is_skipped(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _place_gallery_album(
            gallery, "2024-07-14 - Hiking", album_id=generate_album_id()
        )
        source = _make_source(tmp_path / "src", "2024-07-14 - Hiking")

        result = runner.invoke(
            app, ["gallery", "import", "-a", str(source), "-g", str(gallery)]
        )

        assert result.exit_code == 0
        assert "reimport" in result.output.lower()


class TestClobberGuard:
    def test_different_album_same_name_refused(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        _place_gallery_album(
            gallery, "2024-07-14 - Hiking", album_id=generate_album_id()
        )
        # Source carries a *different* ID than the gallery occupant.
        source = _make_source(
            tmp_path / "src", "2024-07-14 - Hiking", album_id=generate_album_id()
        )

        result = runner.invoke(
            app,
            ["gallery", "import", "-a", str(source), "-g", str(gallery), "--reimport"],
        )

        assert result.exit_code == 1


class TestDryRun:
    def test_dry_run_imports_nothing(self, tmp_path: Path) -> None:
        # No face-model stubbing needed: the analyzer factory is injected
        # lazily and dry-run never reaches face detection.
        gallery = _setup_gallery(tmp_path)
        base = tmp_path / "incoming"
        _make_source(base, "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["gallery", "import-all", "-d", str(base), "-g", str(gallery), "--dry-run"],
        )

        assert result.exit_code == 0
        assert not (gallery / "albums" / "2024" / "2024-07-14 - Hiking").exists()
