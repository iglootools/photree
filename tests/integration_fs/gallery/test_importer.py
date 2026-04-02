"""Tests for photree.gallery.importer module."""

from __future__ import annotations

from pathlib import Path

import pytest

from photree.album.jpeg import noop_convert_single
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import AlbumMetadata, generate_album_id
from photree.fsprotocol import LinkMode
from photree.gallery.store.fs import save_gallery_metadata
from photree.gallery.store.protocol import GalleryMetadata
from photree.gallery.importer import (
    compute_target_dir,
    import_album,
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_gallery(tmp_path: Path) -> Path:
    """Create a gallery directory with .photree/gallery.yaml."""
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata(link_mode=LinkMode.HARDLINK))
    return gallery


def _setup_ios_album(album: Path) -> None:
    """Create a minimal iOS album."""
    _write(album / "ios-main/orig-img/IMG_0001.HEIC", "heic-data")
    _write(album / "ios-main/orig-img/IMG_0001.AAE", "aae-data")
    _write(album / "main-img/IMG_0001.HEIC", "heic-data")
    _write(album / "main-jpg/IMG_0001.jpg", "jpg-data")
    (album / "ios-main/orig-vid").mkdir(parents=True, exist_ok=True)
    (album / "main-vid").mkdir(parents=True, exist_ok=True)


def _setup_std_album(album: Path) -> None:
    """Create a minimal std album."""
    _write(album / "nelu-img/sunset.heic", "heic-data")
    _write(album / "nelu-jpg/sunset.jpg", "jpg-data")


class TestComputeTargetDir:
    def test_standard_album_name(self) -> None:
        result = compute_target_dir(Path("/gallery"), "2024-07-14 - Hiking")
        assert result == Path("/gallery/albums/2024/2024-07-14 - Hiking")

    def test_different_year(self) -> None:
        result = compute_target_dir(Path("/gallery"), "2023-01-01 - New Year")
        assert result == Path("/gallery/albums/2023/2023-01-01 - New Year")

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            compute_target_dir(Path("/gallery"), "no-date-album")


class TestImportAlbum:
    def test_copies_album_to_gallery(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)

        result = import_album(
            source_dir=album,
            gallery_dir=gallery,
            convert_file=noop_convert_single,
        )

        assert result.album_name == "2024-07-14 - Hiking"
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        assert result.target_dir == target
        assert target.is_dir()
        assert (target / "ios-main/orig-img/IMG_0001.HEIC").is_file()

    def test_generates_missing_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)
        # No .photree/album.yaml

        result = import_album(
            source_dir=album,
            gallery_dir=gallery,
            convert_file=noop_convert_single,
        )

        assert result.id_generated
        meta = load_album_metadata(result.target_dir)
        assert meta is not None
        assert meta.id

    def test_preserves_existing_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)
        original_id = generate_album_id()
        save_album_metadata(album, AlbumMetadata(id=original_id))

        result = import_album(
            source_dir=album,
            gallery_dir=gallery,
            convert_file=noop_convert_single,
        )

        assert not result.id_generated
        meta = load_album_metadata(result.target_dir)
        assert meta is not None
        assert meta.id == original_id

    def test_refuses_existing_target(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)

        # Create the target directory first
        target = gallery / "albums" / "2024" / "2024-07-14 - Hiking"
        target.mkdir(parents=True)

        with pytest.raises(ValueError, match="already exists"):
            import_album(
                source_dir=album,
                gallery_dir=gallery,
                convert_file=noop_convert_single,
            )

    def test_dry_run_does_not_copy(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)

        result = import_album(
            source_dir=album,
            gallery_dir=gallery,
            dry_run=True,
            convert_file=noop_convert_single,
        )

        assert not result.target_dir.exists()

    def test_std_album_import(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_std_album(album)

        result = import_album(
            source_dir=album,
            gallery_dir=gallery,
            convert_file=noop_convert_single,
        )

        target = result.target_dir
        assert (target / "nelu-img/sunset.heic").is_file()
        assert not result.optimized  # std albums don't get optimized

    def test_refreshes_stale_jpegs(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)
        # Add an image without a corresponding JPEG to make it stale
        _write(album / "main-img/IMG_0002.HEIC", "heic2")

        result = import_album(
            source_dir=album,
            gallery_dir=gallery,
            convert_file=noop_convert_single,
        )

        assert result.jpeg_refreshed

    def test_rejects_optimize_when_browsable_files_mismatch(
        self, tmp_path: Path
    ) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)
        # Corrupt the browsable copy so it no longer matches the archival source
        _write(album / "main-img/IMG_0001.HEIC", "corrupted-data")

        with pytest.raises(ValueError, match="Pre-optimize integrity check failed"):
            import_album(
                source_dir=album,
                gallery_dir=gallery,
                convert_file=noop_convert_single,
            )

    def test_stage_callbacks_invoked(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)

        stages: list[tuple[str, str]] = []
        import_album(
            source_dir=album,
            gallery_dir=gallery,
            on_stage_start=lambda s: stages.append(("start", s)),
            on_stage_end=lambda s: stages.append(("end", s)),
            convert_file=noop_convert_single,
        )

        stage_names = [name for _, name in stages]
        assert "copy" in stage_names
        assert "id" in stage_names
        assert "jpeg" in stage_names
        assert "optimize" in stage_names
