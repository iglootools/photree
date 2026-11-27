"""Tests for cross-album media index (duplicate media ID detection)."""

from pathlib import Path

from photree.album.id import generate_media_id
from photree.album.refresh import refresh_media_metadata
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    save_media_metadata,
)
from photree.albums.media_index import find_duplicate_media_ids
from tests.testkit import make_album


class TestFindDuplicateMediaIds:
    def test_no_duplicates(self, tmp_path: Path) -> None:
        album1, _ = make_album(tmp_path, "album1")
        album2, _ = make_album(tmp_path, "album2")
        refresh_media_metadata(album1)
        refresh_media_metadata(album2)

        result = find_duplicate_media_ids([album1, album2])

        assert result == {}

    def test_duplicate_detected(self, tmp_path: Path) -> None:
        album1, _ = make_album(tmp_path, "album1")
        album2, _ = make_album(tmp_path, "album2")

        shared_id = generate_media_id()
        for album_dir in [album1, album2]:
            save_media_metadata(
                album_dir,
                MediaMetadata(
                    media_sources={
                        "main": MediaSourceMediaMetadata(
                            images={shared_id: "0001"},
                        ),
                    },
                ),
            )

        result = find_duplicate_media_ids([album1, album2])

        assert shared_id in result
        assert set(result[shared_id]) == {album1, album2}

    def test_albums_without_media_yaml_skipped(self, tmp_path: Path) -> None:
        album1, _ = make_album(tmp_path, "album1")
        album2, _ = make_album(tmp_path, "album2")
        refresh_media_metadata(album1)
        # album2 has no media.yaml

        result = find_duplicate_media_ids([album1, album2])

        assert result == {}

    def test_empty_album_list(self) -> None:
        result = find_duplicate_media_ids([])
        assert result == {}

    def test_video_duplicate_detected(self, tmp_path: Path) -> None:
        album1, _ = make_album(tmp_path, "album1")
        album2, _ = make_album(tmp_path, "album2")

        shared_id = generate_media_id()
        for album_dir in [album1, album2]:
            save_media_metadata(
                album_dir,
                MediaMetadata(
                    media_sources={
                        "main": MediaSourceMediaMetadata(
                            videos={shared_id: "0115"},
                        ),
                    },
                ),
            )

        result = find_duplicate_media_ids([album1, album2])

        assert shared_id in result
