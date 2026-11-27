from collections.abc import Callable
from pathlib import Path

from photree.foundation.gallery_metadata import (
    GALLERY_YAML,
    GalleryMetadata,
    load_gallery_metadata,
    save_gallery_metadata,
)
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.linking import LinkMode
from tests.fakes import invoke_cli


def _init_gallery(gallery_dir: Path, link_mode: LinkMode = LinkMode.HARDLINK) -> None:
    save_gallery_metadata(gallery_dir, GalleryMetadata(link_mode=link_mode))


class TestGalleryMetadataSet:
    def test_updates_link_mode(self, tmp_path: Path) -> None:
        _init_gallery(tmp_path, LinkMode.HARDLINK)
        result = invoke_cli(
            [
                "gallery",
                "metadata",
                "set",
                "-g",
                str(tmp_path),
                "--link-mode",
                "symlink",
            ],
        )
        assert result.exit_code == 0
        assert "link-mode: hardlink -> symlink" in result.output
        loaded = load_gallery_metadata(tmp_path / PHOTREE_DIR / GALLERY_YAML)
        assert loaded.link_mode == LinkMode.SYMLINK

    def test_dry_run_leaves_the_metadata_unchanged(self, tmp_path: Path) -> None:
        _init_gallery(tmp_path, LinkMode.HARDLINK)
        before = (tmp_path / PHOTREE_DIR / GALLERY_YAML).read_bytes()

        result = invoke_cli(
            [
                "gallery",
                "metadata",
                "set",
                "-g",
                str(tmp_path),
                "--link-mode",
                "copy",
                "-n",
            ],
        )

        assert result.exit_code == 0, result.output
        assert result.output.startswith("[dry-run] Would update")
        assert "link-mode: hardlink -> copy" in result.output
        assert (tmp_path / PHOTREE_DIR / GALLERY_YAML).read_bytes() == before

    def test_no_faces_enabled_turns_face_detection_off(self, tmp_path: Path) -> None:
        """Regression: only --faces-enabled existed, so it could not be unset."""
        _init_gallery(tmp_path)

        result = invoke_cli(
            ["gallery", "metadata", "set", "-g", str(tmp_path), "--no-faces-enabled"],
        )

        assert result.exit_code == 0, result.output
        loaded = load_gallery_metadata(tmp_path / PHOTREE_DIR / GALLERY_YAML)
        assert loaded.faces_enabled is False

    def test_no_change_when_same_value(self, tmp_path: Path) -> None:
        _init_gallery(tmp_path, LinkMode.HARDLINK)
        result = invoke_cli(
            [
                "gallery",
                "metadata",
                "set",
                "-g",
                str(tmp_path),
                "--link-mode",
                "hardlink",
            ],
        )
        assert result.exit_code == 0
        assert "already up to date" in result.output

    def test_fails_without_gallery_init(self, tmp_path: Path) -> None:
        result = invoke_cli(
            [
                "gallery",
                "metadata",
                "set",
                "-g",
                str(tmp_path),
                "--link-mode",
                "symlink",
            ],
        )
        assert result.exit_code == 1

    def test_fails_when_no_fields_specified(self, tmp_path: Path) -> None:
        _init_gallery(tmp_path)
        result = invoke_cli(["gallery", "metadata", "set", "-g", str(tmp_path)])
        assert result.exit_code == 2
        assert "No fields specified" in result.output

    def test_all_link_modes(self, tmp_path: Path) -> None:
        for mode in LinkMode:
            _init_gallery(tmp_path, LinkMode.HARDLINK)
            invoke_cli(
                [
                    "gallery",
                    "metadata",
                    "set",
                    "-g",
                    str(tmp_path),
                    "--link-mode",
                    mode.value,
                ],
            )
            loaded = load_gallery_metadata(tmp_path / PHOTREE_DIR / GALLERY_YAML)
            assert loaded.link_mode == mode

    def test_resolves_gallery_from_cwd(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        _init_gallery(tmp_path, LinkMode.HARDLINK)
        child = tmp_path / "subdir"
        child.mkdir()
        chdir(child)
        result = invoke_cli(["gallery", "metadata", "set", "--link-mode", "copy"])
        assert result.exit_code == 0
        loaded = load_gallery_metadata(tmp_path / PHOTREE_DIR / GALLERY_YAML)
        assert loaded.link_mode == LinkMode.COPY
