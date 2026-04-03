"""Tests for media metadata refresh logic."""

from __future__ import annotations

from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.refresh import refresh_media_metadata
from photree.album.store.media_metadata import load_media_metadata
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_ios_album(album_dir: Path) -> None:
    """Create a minimal iOS album with orig-img and orig-vid files."""
    album_dir.mkdir(parents=True, exist_ok=True)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0411.HEIC")
    _write(album_dir / "ios-main" / "orig-vid" / "IMG_0115.MOV")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


def _setup_std_album(album_dir: Path, name: str = "nelu") -> None:
    """Create a std media source with archive."""
    _write(album_dir / f"std-{name}" / "orig-img" / "DSC_1234.JPG")
    _write(album_dir / f"std-{name}" / "orig-img" / "DSC_5678.JPG")
    _write(album_dir / f"std-{name}" / "orig-vid" / "VID_001.MOV")
    (album_dir / f"{name}-img").mkdir(parents=True, exist_ok=True)
    (album_dir / f"{name}-jpg").mkdir(parents=True, exist_ok=True)


class TestRefreshFreshAlbum:
    def test_assigns_ids_to_all_media(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = refresh_media_metadata(album)

        assert len(result.by_media_source) == 1
        ms_name, ms_result = result.by_media_source[0]
        assert ms_name == "main"
        assert ms_result.new_images == 2
        assert ms_result.new_videos == 1
        assert ms_result.removed_images == 0
        assert ms_result.removed_videos == 0

    def test_creates_media_yaml(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        meta = load_media_metadata(album)
        assert meta is not None
        assert len(meta.media_sources["main"].images) == 2
        assert len(meta.media_sources["main"].videos) == 1

    def test_image_keys_are_image_numbers(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        meta = load_media_metadata(album)
        assert meta is not None
        keys = set(meta.media_sources["main"].images.values())
        assert keys == {"0410", "0411"}

    def test_video_keys_are_image_numbers(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        meta = load_media_metadata(album)
        assert meta is not None
        keys = set(meta.media_sources["main"].videos.values())
        assert keys == {"0115"}


class TestRefreshIdempotent:
    def test_no_changes_on_second_run(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)
        meta_before = load_media_metadata(album)

        result = refresh_media_metadata(album)

        meta_after = load_media_metadata(album)
        assert meta_before == meta_after
        _, ms_result = result.by_media_source[0]
        assert ms_result.new_images == 0
        assert ms_result.new_videos == 0
        assert ms_result.removed_images == 0
        assert ms_result.removed_videos == 0
        assert not result.changed

    def test_preserves_existing_uuids(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)
        meta_before = load_media_metadata(album)
        assert meta_before is not None
        uuids_before = set(meta_before.media_sources["main"].images.keys())

        refresh_media_metadata(album)
        meta_after = load_media_metadata(album)
        assert meta_after is not None
        uuids_after = set(meta_after.media_sources["main"].images.keys())

        assert uuids_before == uuids_after


class TestRefreshNewFiles:
    def test_assigns_ids_to_new_files_only(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)
        meta_before = load_media_metadata(album)
        assert meta_before is not None
        uuids_before = set(meta_before.media_sources["main"].images.keys())

        # Add a new file
        _write(album / "ios-main" / "orig-img" / "IMG_0412.HEIC")

        result = refresh_media_metadata(album)
        _, ms_result = result.by_media_source[0]
        assert ms_result.new_images == 1
        assert ms_result.removed_images == 0

        meta_after = load_media_metadata(album)
        assert meta_after is not None
        uuids_after = set(meta_after.media_sources["main"].images.keys())
        assert uuids_before < uuids_after  # subset — all old IDs preserved
        assert len(uuids_after) == 3


class TestRefreshRemovedFiles:
    def test_removes_stale_entries(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        # Remove a file
        (album / "ios-main" / "orig-img" / "IMG_0410.HEIC").unlink()

        result = refresh_media_metadata(album)
        _, ms_result = result.by_media_source[0]
        assert ms_result.removed_images == 1
        assert ms_result.new_images == 0

        meta = load_media_metadata(album)
        assert meta is not None
        assert len(meta.media_sources["main"].images) == 1
        keys = set(meta.media_sources["main"].images.values())
        assert keys == {"0411"}


class TestRefreshMixed:
    def test_add_and_remove(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        refresh_media_metadata(album)

        # Remove one, add another
        (album / "ios-main" / "orig-img" / "IMG_0410.HEIC").unlink()
        _write(album / "ios-main" / "orig-img" / "IMG_0999.HEIC")

        result = refresh_media_metadata(album)
        _, ms_result = result.by_media_source[0]
        assert ms_result.new_images == 1
        assert ms_result.removed_images == 1
        assert result.changed


class TestRefreshDryRun:
    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = refresh_media_metadata(album, dry_run=True)

        assert result.total_new == 3
        assert load_media_metadata(album) is None


class TestRefreshMultipleSources:
    def test_ios_and_std(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        _setup_std_album(album, "nelu")

        result = refresh_media_metadata(album)

        assert len(result.by_media_source) == 2
        names = {name for name, _ in result.by_media_source}
        assert names == {"main", "nelu"}

        meta = load_media_metadata(album)
        assert meta is not None
        assert len(meta.media_sources["main"].images) == 2
        assert len(meta.media_sources["nelu"].images) == 2

        # Std source keys are stems
        std_keys = set(meta.media_sources["nelu"].images.values())
        assert std_keys == {"DSC_1234", "DSC_5678"}
