"""Tests for cross-album media index (duplicate media ID detection)."""

from __future__ import annotations

from pathlib import Path

from photree.album.id import generate_album_id, generate_media_id
from photree.album.refresh import refresh_media_metadata
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    save_media_metadata,
)
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.albums.media_index import find_duplicate_media_ids


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _setup_ios_album(album_dir: Path) -> None:
    album_dir.mkdir(parents=True, exist_ok=True)
    save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))
    _write(album_dir / "ios-main" / "orig-img" / "IMG_0410.HEIC")
    (album_dir / "main-img").mkdir(parents=True, exist_ok=True)
    (album_dir / "main-jpg").mkdir(parents=True, exist_ok=True)


class TestFindDuplicateMediaIds:
    def test_no_duplicates(self, tmp_path: Path) -> None:
        album1 = tmp_path / "album1"
        album2 = tmp_path / "album2"
        _setup_ios_album(album1)
        _setup_ios_album(album2)
        refresh_media_metadata(album1)
        refresh_media_metadata(album2)

        result = find_duplicate_media_ids([album1, album2])

        assert result == {}

    def test_duplicate_detected(self, tmp_path: Path) -> None:
        album1 = tmp_path / "album1"
        album2 = tmp_path / "album2"
        _setup_ios_album(album1)
        _setup_ios_album(album2)

        # Use the same UUID in both albums
        shared_id = generate_media_id()
        for album_dir in [album1, album2]:
            save_media_metadata(
                album_dir,
                MediaMetadata(
                    media_sources={
                        "main": MediaSourceMediaMetadata(
                            images={shared_id: "0410"},
                        ),
                    }
                ),
            )

        result = find_duplicate_media_ids([album1, album2])

        assert shared_id in result
        assert set(result[shared_id]) == {album1, album2}

    def test_albums_without_media_yaml_skipped(self, tmp_path: Path) -> None:
        album1 = tmp_path / "album1"
        album2 = tmp_path / "album2"
        _setup_ios_album(album1)
        _setup_ios_album(album2)
        refresh_media_metadata(album1)
        # album2 has no media.yaml

        result = find_duplicate_media_ids([album1, album2])

        assert result == {}

    def test_empty_album_list(self) -> None:
        result = find_duplicate_media_ids([])
        assert result == {}

    def test_video_duplicate_detected(self, tmp_path: Path) -> None:
        album1 = tmp_path / "album1"
        album2 = tmp_path / "album2"
        _setup_ios_album(album1)
        _setup_ios_album(album2)

        shared_id = generate_media_id()
        for album_dir in [album1, album2]:
            save_media_metadata(
                album_dir,
                MediaMetadata(
                    media_sources={
                        "main": MediaSourceMediaMetadata(
                            videos={shared_id: "0115"},
                        ),
                    }
                ),
            )

        result = find_duplicate_media_ids([album1, album2])

        assert shared_id in result
