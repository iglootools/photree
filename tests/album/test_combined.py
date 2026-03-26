"""Tests for photree.album.combined module."""

import os
from pathlib import Path

from photree.album.combined import RefreshMainDirResult, refresh_main_dir
from photree.fsprotocol import IMG_EXTENSIONS, MOV_EXTENSIONS, LinkMode


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    """Create a directory with the given filenames."""
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


class TestRefreshMainDir:
    def test_uses_rendered_when_available(self, tmp_path: Path) -> None:
        orig = _setup_dir(
            tmp_path / "ios-main/orig-img", ["IMG_0410.HEIC", "IMG_0410.AAE"]
        )
        rendered = _setup_dir(
            tmp_path / "ios-main/edit-img", ["IMG_E0410.HEIC", "IMG_O0410.AAE"]
        )
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=IMG_EXTENSIONS
        )

        assert result.copied == 1
        assert (combined / "IMG_E0410.HEIC").exists()
        assert not (combined / "IMG_0410.HEIC").exists()
        # Metadata files are not copied to combined
        assert not (combined / "IMG_0410.AAE").exists()
        assert not (combined / "IMG_O0410.AAE").exists()

    def test_falls_back_to_orig_when_no_rendered(self, tmp_path: Path) -> None:
        orig = _setup_dir(
            tmp_path / "ios-main/orig-img", ["IMG_0100.HEIC", "IMG_0100.AAE"]
        )
        rendered = tmp_path / "ios-main/edit-img"  # does not exist
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=IMG_EXTENSIONS
        )

        assert result.copied == 1
        assert (combined / "IMG_0100.HEIC").exists()

    def test_mixed_rendered_and_fallback(self, tmp_path: Path) -> None:
        orig = _setup_dir(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0002.HEIC"],
        )
        rendered = _setup_dir(
            tmp_path / "ios-main/edit-img",
            ["IMG_E0001.HEIC"],
        )
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=IMG_EXTENSIONS
        )

        assert result.copied == 2
        assert (combined / "IMG_E0001.HEIC").exists()
        assert (combined / "IMG_0002.HEIC").exists()
        assert not (combined / "IMG_0001.HEIC").exists()

    def test_clears_existing_combined(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        combined = _setup_dir(tmp_path / "main-img", ["IMG_STALE.HEIC"])

        refresh_main_dir(orig, rendered, combined, media_extensions=IMG_EXTENSIONS)

        assert (combined / "IMG_0001.HEIC").exists()
        assert not (combined / "IMG_STALE.HEIC").exists()

    def test_mov_files(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-vid", ["IMG_0115.MOV"])
        rendered = _setup_dir(tmp_path / "ios-main/edit-vid", ["IMG_E0115.MOV"])
        combined = tmp_path / "main-vid"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=MOV_EXTENSIONS
        )

        assert result.copied == 1
        assert (combined / "IMG_E0115.MOV").exists()

    def test_returns_zero_when_orig_missing(self, tmp_path: Path) -> None:
        orig = tmp_path / "ios-main/orig-img"  # does not exist
        rendered = tmp_path / "ios-main/edit-img"
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=IMG_EXTENSIONS
        )

        assert result == RefreshMainDirResult(copied=0)
        assert not combined.exists()

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=IMG_EXTENSIONS, dry_run=True
        )

        assert result.copied == 1
        assert not combined.exists()

    def test_preserves_file_content(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        combined = tmp_path / "main-img"

        refresh_main_dir(orig, rendered, combined, media_extensions=IMG_EXTENSIONS)

        assert (combined / "IMG_E0001.HEIC").read_text() == "data-IMG_E0001.HEIC"

    def test_heic_priority_dedup(self, tmp_path: Path) -> None:
        """When duplicate numbers exist, HEIC is preferred over JPG."""
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = _setup_dir(
            tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC", "IMG_E0001.JPG"]
        )
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=IMG_EXTENSIONS
        )

        assert result.copied == 1
        assert (combined / "IMG_E0001.HEIC").exists()
        assert not (combined / "IMG_E0001.JPG").exists()

    def test_dng_priority_over_heic(self, tmp_path: Path) -> None:
        """When duplicate numbers exist, DNG (ProRAW) is preferred over HEIC."""
        orig = _setup_dir(
            tmp_path / "ios-main/orig-img", ["IMG_0001.DNG", "IMG_0001.HEIC"]
        )
        rendered = tmp_path / "ios-main/edit-img"
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=IMG_EXTENSIONS
        )

        assert result.copied == 1
        assert (combined / "IMG_0001.DNG").exists()
        assert not (combined / "IMG_0001.HEIC").exists()

    def test_ignores_dotfiles(self, tmp_path: Path) -> None:
        orig = _setup_dir(
            tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", ".DS_Store"]
        )
        rendered = tmp_path / "ios-main/edit-img"
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig, rendered, combined, media_extensions=IMG_EXTENSIONS
        )

        assert result.copied == 1
        assert not (combined / ".DS_Store").exists()


class TestRefreshMainDirLinkMode:
    def test_hardlink_mode_creates_hardlinks(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        combined = tmp_path / "main-img"

        refresh_main_dir(
            orig,
            rendered,
            combined,
            media_extensions=IMG_EXTENSIONS,
            link_mode=LinkMode.HARDLINK,
        )

        combined_file = combined / "IMG_0001.HEIC"
        orig_file = orig / "IMG_0001.HEIC"
        assert combined_file.exists()
        assert os.stat(combined_file).st_ino == os.stat(orig_file).st_ino

    def test_symlink_mode_creates_relative_symlinks(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        combined = tmp_path / "main-img"

        refresh_main_dir(
            orig,
            rendered,
            combined,
            media_extensions=IMG_EXTENSIONS,
            link_mode=LinkMode.SYMLINK,
        )

        combined_file = combined / "IMG_0001.HEIC"
        assert combined_file.is_symlink()
        # Target should be relative
        target = os.readlink(combined_file)
        assert not os.path.isabs(target)
        # Should resolve to the original file
        assert combined_file.resolve() == (orig / "IMG_0001.HEIC").resolve()

    def test_copy_mode_creates_independent_copy(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        combined = tmp_path / "main-img"

        refresh_main_dir(
            orig,
            rendered,
            combined,
            media_extensions=IMG_EXTENSIONS,
            link_mode=LinkMode.COPY,
        )

        combined_file = combined / "IMG_0001.HEIC"
        orig_file = orig / "IMG_0001.HEIC"
        assert combined_file.exists()
        assert not combined_file.is_symlink()
        assert os.stat(combined_file).st_ino != os.stat(orig_file).st_ino

    def test_hardlink_clears_existing_before_relinking(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        combined = _setup_dir(tmp_path / "main-img", ["IMG_STALE.HEIC"])

        refresh_main_dir(
            orig,
            rendered,
            combined,
            media_extensions=IMG_EXTENSIONS,
            link_mode=LinkMode.HARDLINK,
        )

        assert (combined / "IMG_0001.HEIC").exists()
        assert not (combined / "IMG_STALE.HEIC").exists()

    def test_dry_run_with_link_mode(self, tmp_path: Path) -> None:
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        combined = tmp_path / "main-img"

        result = refresh_main_dir(
            orig,
            rendered,
            combined,
            media_extensions=IMG_EXTENSIONS,
            link_mode=LinkMode.HARDLINK,
            dry_run=True,
        )

        assert result.copied == 1
        assert not combined.exists()

    def test_hardlink_with_rendered(self, tmp_path: Path) -> None:
        """Hardlink should use rendered when available."""
        orig = _setup_dir(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = _setup_dir(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        combined = tmp_path / "main-img"

        refresh_main_dir(
            orig,
            rendered,
            combined,
            media_extensions=IMG_EXTENSIONS,
            link_mode=LinkMode.HARDLINK,
        )

        combined_file = combined / "IMG_E0001.HEIC"
        rendered_file = rendered / "IMG_E0001.HEIC"
        assert combined_file.exists()
        assert os.stat(combined_file).st_ino == os.stat(rendered_file).st_ino
