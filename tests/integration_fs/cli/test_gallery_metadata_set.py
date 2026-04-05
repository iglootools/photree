"""Tests for ``photree gallery metadata set`` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from photree.cli import app
from photree.fsprotocol import (
    GALLERY_YAML,
    GalleryMetadata,
    LinkMode,
    PHOTREE_DIR,
    load_gallery_metadata,
    save_gallery_metadata,
)

runner = CliRunner()


def _init_gallery(gallery_dir: Path, link_mode: LinkMode = LinkMode.HARDLINK) -> None:
    save_gallery_metadata(gallery_dir, GalleryMetadata(link_mode=link_mode))


class TestGalleryMetadataSet:
    def test_updates_link_mode(self, tmp_path: Path) -> None:
        _init_gallery(tmp_path, LinkMode.HARDLINK)
        result = runner.invoke(
            app,
            [
                "gallery",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--link-mode",
                "symlink",
            ],
        )
        assert result.exit_code == 0
        assert "link-mode: hardlink -> symlink" in result.output
        loaded = load_gallery_metadata(tmp_path / PHOTREE_DIR / GALLERY_YAML)
        assert loaded.link_mode == LinkMode.SYMLINK

    def test_no_change_when_same_value(self, tmp_path: Path) -> None:
        _init_gallery(tmp_path, LinkMode.HARDLINK)
        result = runner.invoke(
            app,
            [
                "gallery",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--link-mode",
                "hardlink",
            ],
        )
        assert result.exit_code == 0
        assert "already up to date" in result.output

    def test_fails_without_gallery_init(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "gallery",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--link-mode",
                "symlink",
            ],
        )
        assert result.exit_code == 1

    def test_fails_when_no_fields_specified(self, tmp_path: Path) -> None:
        _init_gallery(tmp_path)
        result = runner.invoke(
            app,
            ["gallery", "metadata", "set", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "No fields specified" in result.output

    def test_all_link_modes(self, tmp_path: Path) -> None:
        for mode in LinkMode:
            _init_gallery(tmp_path, LinkMode.HARDLINK)
            runner.invoke(
                app,
                [
                    "gallery",
                    "metadata",
                    "set",
                    "-d",
                    str(tmp_path),
                    "--link-mode",
                    mode.value,
                ],
            )
            loaded = load_gallery_metadata(tmp_path / PHOTREE_DIR / GALLERY_YAML)
            assert loaded.link_mode == mode

    def test_resolves_gallery_from_cwd(
        self, tmp_path: Path, monkeypatch: object
    ) -> None:
        _init_gallery(tmp_path, LinkMode.HARDLINK)
        child = tmp_path / "subdir"
        child.mkdir()
        monkeypatch.chdir(child)  # type: ignore[union-attr]
        result = runner.invoke(
            app,
            ["gallery", "metadata", "set", "--link-mode", "copy"],
        )
        assert result.exit_code == 0
        loaded = load_gallery_metadata(tmp_path / PHOTREE_DIR / GALLERY_YAML)
        assert loaded.link_mode == LinkMode.COPY
