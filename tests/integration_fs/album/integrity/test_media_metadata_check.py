"""Tests for media metadata check logic."""

from __future__ import annotations

from pathlib import Path

from photree.album.check.media_metadata import (
    MediaType,
    UnmatchedKey,
    check_media_metadata,
)
from photree.album.id import generate_album_id, generate_media_id
from photree.album.refresh import refresh_media_metadata
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    save_media_metadata,
)
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_ios_album(album_dir: Path) -> None:
    album_dir.mkdir(parents=True, exist_ok=True)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0411.HEIC")
    _write(album_dir / "ios-main" / "orig-vid" / "IMG_0115.MOV")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


class TestMediaMetadataCheckInSync:
    def test_in_sync_after_refresh(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        refresh_media_metadata(album)

        result = check_media_metadata(album)

        assert result.has_media_metadata
        assert result.in_sync
        assert result.image_count == 2
        assert result.video_count == 1
        assert not result.new_keys
        assert not result.stale_keys
        assert not result.duplicate_ids


class TestMediaMetadataCheckMissing:
    def test_missing_media_yaml(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        result = check_media_metadata(album)

        assert not result.has_media_metadata
        assert not result.in_sync


class TestMediaMetadataCheckNewFiles:
    def test_new_files_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        refresh_media_metadata(album)

        # Add a new file
        _write(album / "ios-main" / "orig-img" / "IMG_0412.HEIC")

        result = check_media_metadata(album)

        assert not result.in_sync
        assert len(result.new_keys) == 1
        assert result.new_keys[0] == UnmatchedKey("main", MediaType.IMAGE, "0412")

    def test_new_video_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        refresh_media_metadata(album)

        _write(album / "ios-main" / "orig-vid" / "IMG_0200.MOV")

        result = check_media_metadata(album)

        assert not result.in_sync
        assert len(result.new_keys) == 1
        assert result.new_keys[0] == UnmatchedKey("main", MediaType.VIDEO, "0200")


class TestMediaMetadataCheckStaleFiles:
    def test_removed_files_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        refresh_media_metadata(album)

        (album / "ios-main" / "orig-img" / "IMG_0410.HEIC").unlink()

        result = check_media_metadata(album)

        assert not result.in_sync
        assert len(result.stale_keys) == 1
        assert result.stale_keys[0] == UnmatchedKey("main", MediaType.IMAGE, "0410")


class TestMediaMetadataCheckDuplicateIds:
    def test_duplicate_uuids_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)

        # Manually create media.yaml with a duplicate UUID
        dup_id = generate_media_id()
        save_media_metadata(
            album,
            MediaMetadata(
                media_sources={
                    "main": MediaSourceMediaMetadata(
                        images={dup_id: "0410"},
                        videos={dup_id: "0115"},
                    ),
                }
            ),
        )

        result = check_media_metadata(album)

        assert not result.in_sync
        assert len(result.duplicate_ids) == 1
        assert result.duplicate_ids[0].uuid == dup_id
        assert result.duplicate_ids[0].count == 2


class TestMediaMetadataCheckStaleMediaSource:
    def test_stale_media_source_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        _setup_ios_album(album)
        refresh_media_metadata(album)

        # Add entries for a media source that no longer exists
        meta = MediaMetadata(
            media_sources={
                "main": MediaSourceMediaMetadata(
                    images={generate_media_id(): "0410", generate_media_id(): "0411"},
                    videos={generate_media_id(): "0115"},
                ),
                "deleted": MediaSourceMediaMetadata(
                    images={generate_media_id(): "9999"},
                    videos={},
                ),
            }
        )
        save_media_metadata(album, meta)

        result = check_media_metadata(album)

        assert not result.in_sync
        stale_sources = {k.media_source for k in result.stale_keys}
        assert "deleted" in stale_sources
