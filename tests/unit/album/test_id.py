import uuid

import pytest

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


class TestGenerateAlbumId:
    def test_returns_valid_uuid(self) -> None:
        aid = generate_album_id()
        parsed = uuid.UUID(aid)
        assert parsed.version == 7
