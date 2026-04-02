"""Tests for photree.album.media module."""

from pathlib import Path

import pytest

from photree.album.media import move_media, rm_media, resolve_variants
from photree.album.store.fs import save_album_metadata
from photree.album.store.protocol import (
    AlbumMetadata,
    MAIN_MEDIA_SOURCE,
    generate_album_id,
)

MC = MAIN_MEDIA_SOURCE
PHOTREE_DIR = ".photree"


def _setup_dir(path: Path, filenames: list[str]) -> Path:
    """Create a directory with the given filenames."""
    path.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        (path / name).write_text(f"data-{name}")
    return path


def _names(directory: Path) -> set[str]:
    """Return filenames (names only) in a directory."""
    if not directory.is_dir():
        return set()
    return {f.name for f in directory.iterdir() if f.is_file()}


def _mark_album(album: Path) -> None:
    save_album_metadata(album, AlbumMetadata(id=generate_album_id()))


def _setup_ios_album(album: Path) -> None:
    """Create a minimal iOS album with one image (0410) that has orig, edit, main, jpg."""
    _setup_dir(album / PHOTREE_DIR, [])
    _mark_album(album)
    _setup_dir(
        album / "ios-main/orig-img",
        ["IMG_0410.HEIC", "IMG_0410.AAE"],
    )
    _setup_dir(
        album / "ios-main/edit-img",
        ["IMG_E0410.HEIC", "IMG_O0410.AAE"],
    )
    _setup_dir(album / "main-img", ["IMG_E0410.HEIC"])
    _setup_dir(album / "main-jpg", ["IMG_E0410.jpg"])


def _setup_ios_album_with_video(album: Path) -> None:
    """Create a minimal iOS album with one video (0115)."""
    _setup_dir(album / PHOTREE_DIR, [])
    _mark_album(album)
    _setup_dir(album / "ios-main/orig-img", [])
    _setup_dir(album / "ios-main/orig-vid", ["IMG_0115.MOV"])
    _setup_dir(album / "ios-main/edit-vid", ["IMG_E0115.MOV"])
    _setup_dir(album / "main-vid", ["IMG_E0115.MOV"])


def _setup_std_album(album: Path, media_source_name: str = "nelu") -> None:
    """Create a minimal std contributor album."""
    _setup_dir(album / PHOTREE_DIR, [])
    _mark_album(album)
    _setup_dir(album / f"{media_source_name}-img", ["sunset.heic", "beach.png"])
    _setup_dir(album / f"{media_source_name}-jpg", ["sunset.jpg", "beach.png"])


# ---------------------------------------------------------------------------
# resolve_variants
# ---------------------------------------------------------------------------


class TestResolveVariants:
    def test_ios_image_resolves_all_dirs(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = resolve_variants(album, ["main-jpg/IMG_E0410.jpg"])

        dirs_found = {subdir for subdir, _ in result}
        assert "ios-main/orig-img" in dirs_found
        assert "ios-main/edit-img" in dirs_found
        assert "main-img" in dirs_found
        assert "main-jpg" in dirs_found

    def test_ios_image_finds_all_variants_by_number(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = resolve_variants(album, ["main-jpg/IMG_E0410.jpg"])

        all_files = {f for _, files in result for f in files}
        assert "IMG_0410.HEIC" in all_files
        assert "IMG_0410.AAE" in all_files
        assert "IMG_E0410.HEIC" in all_files
        assert "IMG_O0410.AAE" in all_files
        assert "IMG_E0410.jpg" in all_files

    def test_ios_any_variant_resolves_same(self, tmp_path: Path) -> None:
        """Specifying any variant file resolves the same set."""
        album = tmp_path / "album"
        _setup_ios_album(album)

        from_jpg = resolve_variants(album, ["main-jpg/IMG_E0410.jpg"])
        from_orig = resolve_variants(album, ["ios-main/orig-img/IMG_0410.HEIC"])
        from_edit = resolve_variants(album, ["ios-main/edit-img/IMG_E0410.HEIC"])

        def _all_files(r: list) -> set:
            return {f for _, files in r for f in files}

        assert _all_files(from_jpg) == _all_files(from_orig) == _all_files(from_edit)

    def test_ios_video_resolves_video_dirs(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album_with_video(album)

        result = resolve_variants(album, ["main-vid/IMG_E0115.MOV"])

        dirs_found = {subdir for subdir, _ in result}
        assert "ios-main/orig-vid" in dirs_found
        assert "ios-main/edit-vid" in dirs_found
        assert "main-vid" in dirs_found

    def test_plain_image_resolves_by_stem(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_std_album(album)

        result = resolve_variants(album, ["nelu-img/sunset.heic"])

        dirs_found = {subdir for subdir, _ in result}
        assert "nelu-img" in dirs_found
        assert "nelu-jpg" in dirs_found
        # jpg dir should have sunset.jpg matched by stem
        jpg_files = next(files for d, files in result if d == "nelu-jpg")
        assert "sunset.jpg" in jpg_files

    def test_missing_dir_skipped(self, tmp_path: Path) -> None:
        """Directories that don't exist on disk are silently skipped."""
        album = tmp_path / "album"
        _setup_dir(album / PHOTREE_DIR, [])
        _mark_album(album)
        _setup_dir(album / "ios-main/orig-img", ["IMG_0410.HEIC"])
        _setup_dir(album / "main-img", ["IMG_0410.HEIC"])
        _setup_dir(album / "main-jpg", ["IMG_0410.jpg"])
        # No edit-img dir

        result = resolve_variants(album, ["main-jpg/IMG_0410.jpg"])

        dirs_found = {subdir for subdir, _ in result}
        assert "ios-main/edit-img" not in dirs_found

    def test_invalid_path_raises(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        with pytest.raises(ValueError, match="does not match any media source"):
            resolve_variants(album, ["unknown-dir/IMG_0410.jpg"])

    def test_no_directory_in_path_raises(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        with pytest.raises(ValueError, match="must be a relative path"):
            resolve_variants(album, ["IMG_0410.jpg"])

    def test_multiple_numbers(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_dir(album / PHOTREE_DIR, [])
        _mark_album(album)
        _setup_dir(
            album / "ios-main/orig-img",
            ["IMG_0410.HEIC", "IMG_0411.HEIC"],
        )
        _setup_dir(album / "main-img", ["IMG_0410.HEIC", "IMG_0411.HEIC"])
        _setup_dir(album / "main-jpg", ["IMG_0410.jpg", "IMG_0411.jpg"])

        result = resolve_variants(
            album, ["main-jpg/IMG_0410.jpg", "main-jpg/IMG_0411.jpg"]
        )

        all_files = {f for _, files in result for f in files}
        assert "IMG_0410.HEIC" in all_files
        assert "IMG_0411.HEIC" in all_files
        assert "IMG_0410.jpg" in all_files
        assert "IMG_0411.jpg" in all_files


# ---------------------------------------------------------------------------
# move_media
# ---------------------------------------------------------------------------


class TestMoveMedia:
    def test_ios_moves_all_variants(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        _setup_dir(dst / PHOTREE_DIR, [])
        _mark_album(dst)

        result = move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])

        assert result.total > 0
        # Source dirs should be removed (empty after move)
        assert not (src / "ios-main/orig-img").exists()
        assert not (src / "ios-main/edit-img").exists()
        assert not (src / "ios-main").exists()  # parent also removed
        assert not (src / "main-img").exists()
        assert not (src / "main-jpg").exists()
        # Destination should have everything
        assert "IMG_0410.HEIC" in _names(dst / "ios-main/orig-img")
        assert "IMG_E0410.HEIC" in _names(dst / "ios-main/edit-img")
        assert "IMG_E0410.HEIC" in _names(dst / "main-img")
        assert "IMG_E0410.jpg" in _names(dst / "main-jpg")

    def test_ios_video_moves_all_variants(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album_with_video(src)
        _setup_dir(dst / PHOTREE_DIR, [])
        _mark_album(dst)

        result = move_media(src, dst, ["main-vid/IMG_E0115.MOV"])

        assert result.total > 0
        assert _names(src / "main-vid") == set()
        assert "IMG_E0115.MOV" in _names(dst / "main-vid")
        assert "IMG_0115.MOV" in _names(dst / "ios-main/orig-vid")

    def test_plain_moves_by_stem(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_std_album(src)
        _setup_dir(dst / PHOTREE_DIR, [])
        _mark_album(dst)

        result = move_media(src, dst, ["nelu-img/sunset.heic"])

        assert result.total > 0
        assert "sunset.heic" not in _names(src / "nelu-img")
        assert "sunset.heic" in _names(dst / "nelu-img")
        assert "sunset.jpg" in _names(dst / "nelu-jpg")
        # beach files should stay
        assert "beach.png" in _names(src / "nelu-img")

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        _setup_dir(dst / PHOTREE_DIR, [])
        _mark_album(dst)

        result = move_media(src, dst, ["main-jpg/IMG_E0410.jpg"], dry_run=True)

        assert result.total > 0
        # Source should be unchanged
        assert "IMG_0410.HEIC" in _names(src / "ios-main/orig-img")
        assert "IMG_E0410.jpg" in _names(src / "main-jpg")
        # Destination should be empty
        assert not (dst / "main-jpg").is_dir()

    def test_creates_dest_directories(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        dst.mkdir()

        move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])

        assert (dst / "ios-main/orig-img").is_dir()
        assert (dst / "main-jpg").is_dir()

    def test_keeps_dirs_with_remaining_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_dir(src / PHOTREE_DIR, [])
        _mark_album(src)
        _setup_dir(
            src / "ios-main/orig-img",
            ["IMG_0410.HEIC", "IMG_0411.HEIC"],
        )
        _setup_dir(src / "main-img", ["IMG_0410.HEIC", "IMG_0411.HEIC"])
        _setup_dir(src / "main-jpg", ["IMG_0410.jpg", "IMG_0411.jpg"])
        _setup_dir(dst / PHOTREE_DIR, [])
        _mark_album(dst)

        move_media(src, dst, ["main-jpg/IMG_0410.jpg"])

        # Dirs should still exist because IMG_0411 remains
        assert (src / "ios-main/orig-img").is_dir()
        assert (src / "main-img").is_dir()
        assert (src / "main-jpg").is_dir()
        assert "IMG_0411.HEIC" in _names(src / "ios-main/orig-img")

    def test_refuses_to_overwrite_existing_files(self, tmp_path: Path) -> None:
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_ios_album(src)
        _setup_ios_album(dst)

        with pytest.raises(ValueError, match="would conflict"):
            move_media(src, dst, ["main-jpg/IMG_E0410.jpg"])

        # Source should be unchanged — nothing was moved
        assert "IMG_0410.HEIC" in _names(src / "ios-main/orig-img")

    def test_refuses_on_same_number_different_extension(self, tmp_path: Path) -> None:
        """Detects collision even when the exact filename doesn't match."""
        src = tmp_path / "src-album"
        dst = tmp_path / "dst-album"
        _setup_dir(src / PHOTREE_DIR, [])
        _mark_album(src)
        _setup_dir(src / "ios-main/orig-img", ["IMG_0410.HEIC"])
        _setup_dir(src / "main-img", ["IMG_0410.HEIC"])
        _setup_dir(src / "main-jpg", ["IMG_0410.jpg"])

        _setup_dir(dst / PHOTREE_DIR, [])
        _mark_album(dst)
        # Different extension, same number
        _setup_dir(dst / "ios-main/orig-img", ["IMG_0410.JPG"])
        _setup_dir(dst / "main-img", ["IMG_0410.JPG"])

        with pytest.raises(ValueError, match="would conflict"):
            move_media(src, dst, ["main-jpg/IMG_0410.jpg"])


# ---------------------------------------------------------------------------
# rm_media
# ---------------------------------------------------------------------------


class TestRmMedia:
    def test_ios_removes_all_variants(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = rm_media(album, ["main-jpg/IMG_E0410.jpg"])

        assert result.total > 0
        # Empty dirs should be removed
        assert not (album / "ios-main/orig-img").exists()
        assert not (album / "ios-main/edit-img").exists()
        assert not (album / "ios-main").exists()
        assert not (album / "main-img").exists()
        assert not (album / "main-jpg").exists()

    def test_plain_removes_by_stem(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_std_album(album)

        result = rm_media(album, ["nelu-img/sunset.heic"])

        assert result.total > 0
        assert "sunset.heic" not in _names(album / "nelu-img")
        assert "sunset.jpg" not in _names(album / "nelu-jpg")
        # beach files should stay
        assert "beach.png" in _names(album / "nelu-img")

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = rm_media(album, ["main-jpg/IMG_E0410.jpg"], dry_run=True)

        assert result.total > 0
        assert "IMG_0410.HEIC" in _names(album / "ios-main/orig-img")
        assert "IMG_E0410.jpg" in _names(album / "main-jpg")

    def test_ios_video_removes_all_variants(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album_with_video(album)

        result = rm_media(album, ["main-vid/IMG_E0115.MOV"])

        assert result.total > 0
        assert _names(album / "ios-main/orig-vid") == set()
        assert _names(album / "ios-main/edit-vid") == set()
        assert _names(album / "main-vid") == set()
