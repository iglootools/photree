"""CLI tests for the system-dependency gate.

Batch operations probe ``sips`` / ``exiftool`` before doing any work, so a
machine missing one fails the whole run up front instead of failing every
album individually, halfway through.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata, ios_import_dir
from photree.cli import app
from photree.common.sysdeps import SystemDependency
from photree.fsprotocol import GalleryMetadata, LinkMode, save_gallery_metadata

runner = CliRunner()

SEL_DIR = ios_import_dir("main")


@pytest.fixture
def only_deps(tmp_path_factory, monkeypatch: pytest.MonkeyPatch):
    """Return a factory that restricts PATH to the named dependencies.

    PATH is the real input the gate reads, so shaping it exercises the
    production code path rather than patching over it.
    """

    def _configure(*present: SystemDependency) -> Path:
        bin_dir = tmp_path_factory.mktemp("only-deps-bin")
        for dependency in present:
            stub = bin_dir / str(dependency)
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        monkeypatch.setenv("PATH", str(bin_dir))
        return bin_dir

    return _configure


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _image_capture_dir(tmp_path: Path) -> Path:
    ic_dir = tmp_path / "image_capture"
    for name in ("IMG_0001.HEIC", "IMG_0001.AAE"):
        _write(ic_dir / name)
    return ic_dir


def _staged_album(parent: Path, name: str) -> Path:
    album = parent / name
    _write(album / SEL_DIR / "IMG_0001.HEIC")
    return album


def _gallery(tmp_path: Path) -> Path:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(
        gallery, GalleryMetadata(link_mode=LinkMode.HARDLINK, faces_enabled=False)
    )
    return gallery


class TestAlbumsImportGate:
    def test_missing_exiftool_aborts_before_importing_anything(
        self, tmp_path: Path, only_deps
    ) -> None:
        only_deps(SystemDependency.SIPS)
        ic_dir = _image_capture_dir(tmp_path)
        albums_dir = tmp_path / "albums"
        album = _staged_album(albums_dir, "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["albums", "import", "-d", str(albums_dir), "-s", str(ic_dir)],
        )

        assert result.exit_code == 1
        assert "exiftool" in result.output
        # The staging entry is untouched and no archive was created.
        assert (album / SEL_DIR / "IMG_0001.HEIC").exists()
        assert not (album / "ios-main").exists()

    def test_missing_sips_aborts(self, tmp_path: Path, only_deps) -> None:
        only_deps(SystemDependency.EXIFTOOL)
        ic_dir = _image_capture_dir(tmp_path)
        albums_dir = tmp_path / "albums"
        album = _staged_album(albums_dir, "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            ["albums", "import", "-d", str(albums_dir), "-s", str(ic_dir)],
        )

        assert result.exit_code == 1
        assert "sips" in result.output
        assert not (album / "ios-main").exists()

    def test_skip_heic_to_jpeg_drops_the_sips_requirement(
        self, tmp_path: Path, only_deps
    ) -> None:
        only_deps(SystemDependency.EXIFTOOL)
        ic_dir = _image_capture_dir(tmp_path)
        albums_dir = tmp_path / "albums"
        _staged_album(albums_dir, "2024-07-14 - Hiking")

        result = runner.invoke(
            app,
            [
                "albums",
                "import",
                "-d",
                str(albums_dir),
                "-s",
                str(ic_dir),
                "--skip-heic-to-jpeg",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "sips" not in result.output


class TestAlbumImportGate:
    def test_missing_exiftool_aborts(self, tmp_path: Path, only_deps) -> None:
        only_deps(SystemDependency.SIPS)
        ic_dir = _image_capture_dir(tmp_path)
        album = _staged_album(tmp_path / "albums", "2024-07-14 - Hiking")

        result = runner.invoke(
            app, ["album", "import", "-a", str(album), "-s", str(ic_dir)]
        )

        assert result.exit_code == 1
        assert "exiftool" in result.output
        assert not (album / "ios-main").exists()


class TestGalleryImportGate:
    def test_import_all_aborts_before_touching_the_gallery(
        self, tmp_path: Path, only_deps
    ) -> None:
        only_deps(SystemDependency.SIPS)
        gallery = _gallery(tmp_path)
        base = tmp_path / "incoming"
        source = base / "2024-07-14 - Hiking"
        _write(source / "ios-main/orig-img/IMG_0001.HEIC")
        save_album_metadata(source, AlbumMetadata(id=generate_album_id()))

        result = runner.invoke(
            app, ["gallery", "import-all", "-d", str(base), "-g", str(gallery)]
        )

        assert result.exit_code == 1
        assert "exiftool" in result.output
        assert not (gallery / "albums").exists()


class TestRefreshGate:
    def test_album_refresh_aborts(self, tmp_path: Path, only_deps) -> None:
        only_deps(SystemDependency.SIPS)
        album = tmp_path / "2024-07-14 - Hiking"
        _write(album / "ios-main/orig-img/IMG_0001.HEIC")
        save_album_metadata(album, AlbumMetadata(id=generate_album_id()))

        result = runner.invoke(app, ["album", "refresh", "-a", str(album)])

        assert result.exit_code == 1
        assert "exiftool" in result.output


class TestCheckSystemCmd:
    def test_reports_missing_dependencies(self, only_deps) -> None:
        only_deps()

        result = runner.invoke(app, ["check", "system"])

        assert result.exit_code == 1
        assert "sips" in result.output
        assert "exiftool" in result.output

    def test_passes_when_all_present(self, only_deps) -> None:
        only_deps(*SystemDependency)

        result = runner.invoke(app, ["check", "system"])

        assert result.exit_code == 0


def test_path_fixture_shapes_the_real_probe(only_deps) -> None:
    """Guard the fixture itself: PATH really is what the gate reads."""
    bin_dir = only_deps(SystemDependency.EXIFTOOL)
    assert os.environ["PATH"] == str(bin_dir)
