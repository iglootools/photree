"""Tests for photree.gallery.importer module."""

from __future__ import annotations

from pathlib import Path

import pytest

from photree.album.id import generate_album_id
from photree.album.jpeg import copy_convert_single, noop_convert_single
from photree.album.refresh import AlbumRefreshResult
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.dates import DatePrefixError
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from photree.foundation.linking import LinkMode
from photree.gallery.importer import (
    TargetExistsError,
    compute_target_dir,
    import_album,
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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

    def test_month_and_year_precision_albums(self) -> None:
        # Valid names at every date precision land under their (start) year.
        assert compute_target_dir(Path("/gallery"), "2024-07 - Summer") == Path(
            "/gallery/albums/2024/2024-07 - Summer"
        )
        assert compute_target_dir(Path("/gallery"), "2024 - Family") == Path(
            "/gallery/albums/2024/2024 - Family"
        )

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(DatePrefixError) as exc_info:
            compute_target_dir(Path("/gallery"), "no-date-album")
        assert exc_info.value.name == "no-date-album"


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

        with pytest.raises(TargetExistsError) as exc_info:
            import_album(
                source_dir=album,
                gallery_dir=gallery,
                convert_file=noop_convert_single,
            )
        assert exc_info.value.target == target

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

    def test_refreshes_stale_jpegs(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)
        # Add an image to both archive and browsable without a JPEG
        _write(album / "ios-main/orig-img/IMG_0002.HEIC", "heic2")
        _write(album / "main-img/IMG_0002.HEIC", "heic2")

        result = import_album(
            source_dir=album,
            gallery_dir=gallery,
            convert_file=copy_convert_single,
        )

        # Unified pipeline rebuilds JPEGs when stale
        assert (result.target_dir / "main-jpg/IMG_0002.jpg").is_file()

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
        assert "refresh-derived" in stage_names

    def test_failed_refresh_leaves_no_partial_album(self, tmp_path: Path) -> None:
        """Regression: a half-built target was later skipped as "imported"."""
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)

        class RefreshFailed(Exception):
            pass

        def failing_refresh(*_args: object, **_kwargs: object) -> AlbumRefreshResult:
            raise RefreshFailed

        with pytest.raises(RefreshFailed):
            import_album(
                source_dir=album,
                gallery_dir=gallery,
                convert_file=noop_convert_single,
                refresh=failing_refresh,
            )

        year_dir = gallery / "albums" / "2024"
        assert list(year_dir.iterdir()) == []

    def test_uses_injected_id(self, tmp_path: Path) -> None:
        gallery = _setup_gallery(tmp_path)
        album = tmp_path / "2024-07-14 - Hiking"
        _setup_ios_album(album)
        fixed_id = generate_album_id()

        result = import_album(
            source_dir=album,
            gallery_dir=gallery,
            convert_file=noop_convert_single,
            new_id=lambda: fixed_id,
        )

        meta = load_album_metadata(result.target_dir)
        assert meta is not None and meta.id == fixed_id
