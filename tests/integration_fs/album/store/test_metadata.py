import uuid
from pathlib import Path

import pytest
import yaml

from photree.album.id import (
    IMAGE_ID_PREFIX,
    VIDEO_ID_PREFIX,
    InvalidExternalIdError,
    InvalidExternalIdKind,
    format_album_external_id,
    format_external_id,
    format_image_external_id,
    format_video_external_id,
    generate_album_id,
    generate_media_id,
    parse_external_id,
)
from photree.album.store.album_discovery import (
    discover_albums,
    discover_potential_albums,
    has_media_sources,
    is_album,
)
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import ALBUM_YAML, AlbumMetadata
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.metadata_io import (
    InvalidMetadataError,
)
from tests.testkit import add_ios_media_source, mark_album


class TestExternalId:
    def test_roundtrip(self) -> None:
        internal = str(uuid.uuid4())
        external = format_external_id("album", internal)
        assert parse_external_id(external, "album") == internal

    def test_format_starts_with_prefix(self) -> None:
        internal = str(uuid.uuid4())
        external = format_album_external_id(internal)
        assert external.startswith("album_")

    def test_reasonable_length(self) -> None:
        internal = str(uuid.uuid4())
        external = format_album_external_id(internal)
        # prefix (5) + underscore (1) + base58 (~22) = ~28 chars
        assert 20 < len(external) < 35

    def test_parse_wrong_prefix_raises(self) -> None:
        internal = str(uuid.uuid4())
        external = format_external_id("album", internal)
        with pytest.raises(InvalidExternalIdError) as exc_info:
            parse_external_id(external, "gallery")
        assert exc_info.value.expected_prefix == "gallery"
        assert exc_info.value.value == external
        assert exc_info.value.kind == InvalidExternalIdKind.WRONG_PREFIX

    def test_parse_no_underscore_raises(self) -> None:
        with pytest.raises(InvalidExternalIdError) as exc_info:
            parse_external_id("nounderscore", "album")
        assert exc_info.value.kind == InvalidExternalIdKind.WRONG_PREFIX

    def test_parse_malformed_base58_raises(self) -> None:
        # "0" is not in the base58 alphabet.
        with pytest.raises(InvalidExternalIdError) as exc_info:
            parse_external_id("album_0abc", "album")
        assert exc_info.value.kind == InvalidExternalIdKind.MALFORMED
        assert exc_info.value.value == "album_0abc"


class TestMediaExternalId:
    def test_image_roundtrip(self) -> None:
        internal = str(uuid.uuid4())
        external = format_image_external_id(internal)
        assert parse_external_id(external, IMAGE_ID_PREFIX) == internal

    def test_video_roundtrip(self) -> None:
        internal = str(uuid.uuid4())
        external = format_video_external_id(internal)
        assert parse_external_id(external, VIDEO_ID_PREFIX) == internal

    def test_image_starts_with_prefix(self) -> None:
        internal = str(uuid.uuid4())
        assert format_image_external_id(internal).startswith("image_")

    def test_video_starts_with_prefix(self) -> None:
        internal = str(uuid.uuid4())
        assert format_video_external_id(internal).startswith("video_")

    def test_parse_image_wrong_prefix_raises(self) -> None:
        internal = str(uuid.uuid4())
        external = format_video_external_id(internal)
        with pytest.raises(InvalidExternalIdError) as exc_info:
            parse_external_id(external, IMAGE_ID_PREFIX)
        assert exc_info.value.expected_prefix == "image"
        assert exc_info.value.value == external

    def test_parse_video_wrong_prefix_raises(self) -> None:
        internal = str(uuid.uuid4())
        external = format_image_external_id(internal)
        with pytest.raises(InvalidExternalIdError) as exc_info:
            parse_external_id(external, VIDEO_ID_PREFIX)
        assert exc_info.value.expected_prefix == "video"
        assert exc_info.value.value == external


class TestGenerateMediaId:
    def test_returns_valid_uuid(self) -> None:
        mid = generate_media_id()
        parsed = uuid.UUID(mid)
        assert parsed.version == 7

    def test_unique_ids(self) -> None:
        ids = {generate_media_id() for _ in range(100)}
        assert len(ids) == 100


class TestAlbumMetadata:
    def test_yaml_roundtrip(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        meta = AlbumMetadata(id=generate_album_id())

        save_album_metadata(album, meta)
        loaded = load_album_metadata(album)

        assert loaded is not None
        assert loaded.id == meta.id

    def test_yaml_uses_kebab_case(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_album_metadata(album, AlbumMetadata(id="test-id"))

        raw = yaml.safe_load((album / PHOTREE_DIR / ALBUM_YAML).read_text())
        assert "id" in raw

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_album_metadata(tmp_path) is None

    def test_load_empty_file_raises(self, tmp_path: Path) -> None:
        photree_dir = tmp_path / PHOTREE_DIR
        photree_dir.mkdir()
        (photree_dir / ALBUM_YAML).write_text("")
        with pytest.raises(InvalidMetadataError) as exc_info:
            load_album_metadata(tmp_path)
        assert exc_info.value.path == photree_dir / ALBUM_YAML

    def test_load_truncated_file_raises(self, tmp_path: Path) -> None:
        photree_dir = tmp_path / PHOTREE_DIR
        photree_dir.mkdir()
        (photree_dir / ALBUM_YAML).write_text("id: [0192d4e1", encoding="utf-8")
        with pytest.raises(InvalidMetadataError) as exc_info:
            load_album_metadata(tmp_path)
        assert exc_info.value.path == photree_dir / ALBUM_YAML

    def test_load_mapping_without_id_raises(self, tmp_path: Path) -> None:
        photree_dir = tmp_path / PHOTREE_DIR
        photree_dir.mkdir()
        (photree_dir / ALBUM_YAML).write_text("other: 1\n", encoding="utf-8")
        with pytest.raises(InvalidMetadataError):
            load_album_metadata(tmp_path)

    def test_save_creates_photree_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        album.mkdir()
        save_album_metadata(album, AlbumMetadata(id="test"))
        assert (album / PHOTREE_DIR / ALBUM_YAML).is_file()


class TestGenerateAlbumId:
    def test_returns_valid_uuid(self) -> None:
        aid = generate_album_id()
        parsed = uuid.UUID(aid)
        assert parsed.version == 7


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
