"""CLI tests for ``gallery init``."""

from collections.abc import Callable
from pathlib import Path

from photree.foundation.gallery_metadata import GALLERY_YAML, load_gallery_metadata
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.linking import LinkMode
from tests.fakes import fake_runtime, invoke_cli


def _gallery_yaml(gallery: Path) -> Path:
    return gallery / PHOTREE_DIR / GALLERY_YAML


class TestGalleryInit:
    def test_writes_the_link_mode(self, tmp_path: Path) -> None:
        result = invoke_cli(
            ["gallery", "init", "-g", str(tmp_path), "--link-mode", "copy"],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert "(link-mode: copy)" in result.output
        metadata = load_gallery_metadata(_gallery_yaml(tmp_path))
        assert metadata.link_mode is LinkMode.COPY

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        result = invoke_cli(
            ["gallery", "init", "-g", str(tmp_path), "--dry-run"],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert result.output.startswith("[dry-run] Would create")
        assert not (tmp_path / PHOTREE_DIR).exists()

    def test_defaults_to_hardlink(self, tmp_path: Path) -> None:
        result = invoke_cli(
            ["gallery", "init", "-g", str(tmp_path)],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        metadata = load_gallery_metadata(_gallery_yaml(tmp_path))
        assert metadata.link_mode is LinkMode.HARDLINK

    def test_refuses_to_overwrite_an_existing_gallery(self, tmp_path: Path) -> None:
        invoke_cli(
            ["gallery", "init", "-g", str(tmp_path), "--link-mode", "copy"],
            runtime=fake_runtime(),
        )
        before = _gallery_yaml(tmp_path).read_bytes()

        result = invoke_cli(
            ["gallery", "init", "-g", str(tmp_path), "--link-mode", "symlink"],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 1
        assert "Gallery already initialized" in result.output
        assert "photree gallery metadata set" in result.output
        assert _gallery_yaml(tmp_path).read_bytes() == before

    def test_already_initialized_hint_names_the_gallery_from_outside_it(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        gallery = tmp_path / "gallery"
        gallery.mkdir()
        chdir(tmp_path)
        invoke_cli(["gallery", "init", "-g", str(gallery)], runtime=fake_runtime())

        result = invoke_cli(
            ["gallery", "init", "-g", str(gallery)],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 1
        assert (
            "'photree gallery metadata set --gallery-dir \"gallery\"'" in result.output
        )

    def test_next_steps_name_the_gallery_from_outside_it(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        gallery = tmp_path / "gallery"
        gallery.mkdir()
        chdir(tmp_path)

        result = invoke_cli(
            ["gallery", "init", "-g", str(gallery)],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert 'photree gallery check --gallery-dir "gallery"' in result.output
        assert (
            'photree gallery import -a <album-dir> --gallery-dir "gallery"'
            in result.output
        )

    def test_next_steps_omit_the_gallery_from_inside_it(
        self,
        tmp_path: Path,
        chdir: Callable[[Path], None],
    ) -> None:
        chdir(tmp_path)

        result = invoke_cli(["gallery", "init"], runtime=fake_runtime())

        assert result.exit_code == 0, result.output
        assert "--gallery-dir" not in result.output
        assert "photree gallery check\n" in result.output
