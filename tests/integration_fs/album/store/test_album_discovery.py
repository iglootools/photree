from pathlib import Path

from photree.album.id import (
    generate_album_id,
)
from photree.album.store.album_discovery import (
    discover_albums,
    discover_potential_albums,
    has_media_sources,
    is_album,
)
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.foundation.layout import PHOTREE_DIR
from tests.testkit import add_ios_media_source, mark_album


class TestIsAlbum:
    def test_album_with_metadata(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_ios_media_source(album)
        mark_album(album)
        assert is_album(album)

    def test_legacy_album_not_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_ios_media_source(album)
        (album / PHOTREE_DIR).mkdir(parents=True, exist_ok=True)
        assert not is_album(album)

    def test_no_media_source_not_detected(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
        assert not is_album(album)


class TestDiscoverAlbums:
    def test_discovers_proper_albums(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_ios_media_source(album)
        mark_album(album)

        albums = discover_albums(tmp_path)
        assert albums == [album]

    def test_skips_legacy_albums(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_ios_media_source(album)
        (album / PHOTREE_DIR).mkdir(parents=True, exist_ok=True)

        albums = discover_albums(tmp_path)
        assert albums == []


class TestHasMediaSources:
    def test_with_ios_media_source(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_ios_media_source(album)
        assert has_media_sources(album) is True

    def test_empty_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        assert has_media_sources(album) is False


class TestDiscoverPotentialAlbums:
    def test_finds_albums_without_metadata(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_ios_media_source(album)
        # No _mark_album — no album.yaml

        albums, skipped = discover_potential_albums(tmp_path)
        assert albums == [album]
        assert skipped == []

    def test_finds_albums_with_metadata(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_ios_media_source(album)
        mark_album(album)

        albums, skipped = discover_potential_albums(tmp_path)
        assert albums == [album]
        assert skipped == []

    def test_skips_empty_dirs(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        albums, skipped = discover_potential_albums(tmp_path)
        assert albums == []
        assert skipped == [empty]

    def test_partitions_albums_and_non_albums(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_ios_media_source(album)
        non_album = tmp_path / "new"
        non_album.mkdir()

        albums, skipped = discover_potential_albums(tmp_path)
        assert albums == [album]
        assert skipped == [non_album]

    def test_skipped_includes_intermediate_levels(self, tmp_path: Path) -> None:
        container = tmp_path / "trip"
        container.mkdir()
        album = container / "album"
        add_ios_media_source(album)

        albums, skipped = discover_potential_albums(tmp_path)
        assert albums == [album]
        assert skipped == [container]
