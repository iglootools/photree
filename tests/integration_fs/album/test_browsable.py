from pathlib import Path

from photree.album.browsable import RefreshBrowsableDirResult, refresh_browsable_dir
from photree.album.formats import IMG_EXTENSIONS, VID_EXTENSIONS
from photree.album.store.media_source import ios_img_number, stem_key
from photree.foundation.linking import LinkMode
from tests.testkit import write_files


class TestRefreshBrowsableDir:
    def test_uses_rendered_when_available(self, tmp_path: Path) -> None:
        orig = write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0410.HEIC", "IMG_0410.AAE"],
        )
        rendered = write_files(
            tmp_path / "ios-main/edit-img",
            ["IMG_E0410.HEIC", "IMG_O0410.AAE"],
        )
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert result.copied == 1
        assert (browsable / "IMG_E0410.HEIC").exists()
        assert not (browsable / "IMG_0410.HEIC").exists()
        # Metadata files are not copied to browsable
        assert not (browsable / "IMG_0410.AAE").exists()
        assert not (browsable / "IMG_O0410.AAE").exists()

    def test_falls_back_to_orig_when_no_rendered(self, tmp_path: Path) -> None:
        orig = write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0100.HEIC", "IMG_0100.AAE"],
        )
        rendered = tmp_path / "ios-main/edit-img"  # does not exist
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert result.copied == 1
        assert (browsable / "IMG_0100.HEIC").exists()

    def test_mixed_rendered_and_fallback(self, tmp_path: Path) -> None:
        orig = write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0002.HEIC"],
        )
        rendered = write_files(
            tmp_path / "ios-main/edit-img",
            ["IMG_E0001.HEIC"],
        )
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert result.copied == 2
        assert (browsable / "IMG_E0001.HEIC").exists()
        assert (browsable / "IMG_0002.HEIC").exists()
        assert not (browsable / "IMG_0001.HEIC").exists()

    def test_clears_existing_browsable(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        browsable = write_files(tmp_path / "main-img", ["IMG_STALE.HEIC"])

        refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert (browsable / "IMG_0001.HEIC").exists()
        assert not (browsable / "IMG_STALE.HEIC").exists()

    def test_mov_files(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-vid", ["IMG_0115.MOV"])
        rendered = write_files(tmp_path / "ios-main/edit-vid", ["IMG_E0115.MOV"])
        browsable = tmp_path / "main-vid"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=VID_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert result.copied == 1
        assert (browsable / "IMG_E0115.MOV").exists()

    def test_returns_zero_when_orig_missing(self, tmp_path: Path) -> None:
        orig = tmp_path / "ios-main/orig-img"  # does not exist
        rendered = tmp_path / "ios-main/edit-img"
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert result == RefreshBrowsableDirResult(copied=0)
        assert not browsable.exists()

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            dry_run=True,
        )

        assert result.copied == 1
        assert not browsable.exists()

    def test_preserves_file_content(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        browsable = tmp_path / "main-img"

        refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert (browsable / "IMG_E0001.HEIC").read_text() == "data-IMG_E0001.HEIC"

    def test_heic_priority_dedup(self, tmp_path: Path) -> None:
        """When duplicate numbers exist, HEIC is preferred over JPG."""
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = write_files(
            tmp_path / "ios-main/edit-img",
            ["IMG_E0001.HEIC", "IMG_E0001.JPG"],
        )
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert result.copied == 1
        assert (browsable / "IMG_E0001.HEIC").exists()
        assert not (browsable / "IMG_E0001.JPG").exists()

    def test_dng_priority_over_heic(self, tmp_path: Path) -> None:
        """When duplicate numbers exist, DNG (ProRAW) is preferred over HEIC."""
        orig = write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.DNG", "IMG_0001.HEIC"],
        )
        rendered = tmp_path / "ios-main/edit-img"
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert result.copied == 1
        assert (browsable / "IMG_0001.DNG").exists()
        assert not (browsable / "IMG_0001.HEIC").exists()

    def test_ignores_dotfiles(self, tmp_path: Path) -> None:
        orig = write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", ".DS_Store"],
        )
        rendered = tmp_path / "ios-main/edit-img"
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
        )

        assert result.copied == 1
        assert not (browsable / ".DS_Store").exists()


class TestRefreshBrowsableDirLinkMode:
    def test_hardlink_mode_creates_hardlinks(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        browsable = tmp_path / "main-img"

        refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.HARDLINK,
        )

        browsable_file = browsable / "IMG_0001.HEIC"
        orig_file = orig / "IMG_0001.HEIC"
        assert browsable_file.exists()
        assert browsable_file.stat().st_ino == orig_file.stat().st_ino

    def test_symlink_mode_creates_relative_symlinks(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        browsable = tmp_path / "main-img"

        refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.SYMLINK,
        )

        browsable_file = browsable / "IMG_0001.HEIC"
        assert browsable_file.is_symlink()
        target = browsable_file.readlink()
        assert not target.is_absolute()
        assert browsable_file.resolve() == (orig / "IMG_0001.HEIC").resolve()

    def test_copy_mode_creates_independent_copy(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        browsable = tmp_path / "main-img"

        refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.COPY,
        )

        browsable_file = browsable / "IMG_0001.HEIC"
        orig_file = orig / "IMG_0001.HEIC"
        assert browsable_file.exists()
        assert not browsable_file.is_symlink()
        assert browsable_file.stat().st_ino != orig_file.stat().st_ino

    def test_hardlink_clears_existing_before_relinking(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        browsable = write_files(tmp_path / "main-img", ["IMG_STALE.HEIC"])

        refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.HARDLINK,
        )

        assert (browsable / "IMG_0001.HEIC").exists()
        assert not (browsable / "IMG_STALE.HEIC").exists()

    def test_dry_run_with_link_mode(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = tmp_path / "ios-main/edit-img"
        browsable = tmp_path / "main-img"

        result = refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.HARDLINK,
            dry_run=True,
        )

        assert result.copied == 1
        assert not browsable.exists()

    def test_hardlink_with_rendered(self, tmp_path: Path) -> None:
        """Hardlink should use rendered when available."""
        orig = write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC"])
        rendered = write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC"])
        browsable = tmp_path / "main-img"

        refresh_browsable_dir(
            orig,
            rendered,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ios_img_number,
            link_mode=LinkMode.HARDLINK,
        )

        browsable_file = browsable / "IMG_E0001.HEIC"
        rendered_file = rendered / "IMG_E0001.HEIC"
        assert browsable_file.exists()
        assert browsable_file.stat().st_ino == rendered_file.stat().st_ino


class TestRefreshBrowsableDirStd:
    """Tests for refresh_browsable_dir with std filenames (stem-based matching)."""

    def test_picks_orig_by_stem(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        edit = tmp_path / "std-nelu/edit-img"  # does not exist
        browsable = tmp_path / "nelu-img"

        result = refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=stem_key,
        )

        assert result.copied == 2
        assert (browsable / "sunset.heic").exists()
        assert (browsable / "beach.png").exists()

    def test_edit_overrides_orig_by_stem(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic", "beach.png"])
        edit = write_files(tmp_path / "std-nelu/edit-img", ["sunset.jpg"])
        browsable = tmp_path / "nelu-img"

        result = refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=stem_key,
        )

        assert result.copied == 2
        # Edit wins for "sunset" stem
        assert (browsable / "sunset.jpg").exists()
        assert not (browsable / "sunset.heic").exists()
        # No edit for "beach" stem — orig used
        assert (browsable / "beach.png").exists()

    def test_mixed_edit_and_orig(self, tmp_path: Path) -> None:
        orig = write_files(
            tmp_path / "std-nelu/orig-img",
            ["sunset.heic", "beach.png", "mountains.jpg"],
        )
        edit = write_files(
            tmp_path / "std-nelu/edit-img",
            ["sunset.jpg", "mountains.jpg"],
        )
        browsable = tmp_path / "nelu-img"

        result = refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=stem_key,
        )

        assert result.copied == 3
        assert (browsable / "sunset.jpg").exists()
        assert (browsable / "beach.png").exists()
        assert (browsable / "mountains.jpg").exists()
        assert not (browsable / "sunset.heic").exists()

    def test_returns_zero_when_orig_missing(self, tmp_path: Path) -> None:
        orig = tmp_path / "std-nelu/orig-img"  # does not exist
        edit = tmp_path / "std-nelu/edit-img"
        browsable = tmp_path / "nelu-img"

        result = refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=stem_key,
        )

        assert result == RefreshBrowsableDirResult(copied=0)
        assert not browsable.exists()

    def test_clears_existing_browsable(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        edit = tmp_path / "std-nelu/edit-img"
        browsable = write_files(tmp_path / "nelu-img", ["stale.heic"])

        refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=stem_key,
        )

        assert (browsable / "sunset.heic").exists()
        assert not (browsable / "stale.heic").exists()

    def test_video_files_by_stem(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "std-nelu/orig-vid", ["clip.mov"])
        edit = write_files(tmp_path / "std-nelu/edit-vid", ["clip.mov"])
        browsable = tmp_path / "nelu-vid"

        result = refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=VID_EXTENSIONS,
            key_fn=stem_key,
        )

        assert result.copied == 1
        # Edit wins
        assert (browsable / "clip.mov").exists()

    def test_preserves_file_content(self, tmp_path: Path) -> None:
        orig = write_files(tmp_path / "std-nelu/orig-img", ["sunset.heic"])
        edit = write_files(tmp_path / "std-nelu/edit-img", ["sunset.jpg"])
        browsable = tmp_path / "nelu-img"

        refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=stem_key,
        )

        assert (browsable / "sunset.jpg").read_text() == "data-sunset.jpg"

    def test_dedup_priority_dng_over_heic(self, tmp_path: Path) -> None:
        """When orig has both DNG and HEIC for the same stem, DNG wins."""
        orig = write_files(tmp_path / "std-nelu/orig-img", ["photo.dng", "photo.heic"])
        edit = tmp_path / "std-nelu/edit-img"
        browsable = tmp_path / "nelu-img"

        result = refresh_browsable_dir(
            orig,
            edit,
            browsable,
            media_extensions=IMG_EXTENSIONS,
            key_fn=stem_key,
        )

        assert result.copied == 1
        assert (browsable / "photo.dng").exists()
        assert not (browsable / "photo.heic").exists()
