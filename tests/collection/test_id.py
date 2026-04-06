"""Tests for collection ID generation, formatting, and parsing."""

from __future__ import annotations

import pytest

from photree.collection.id import (
    COLLECTION_ID_PREFIX,
    format_collection_external_id,
    generate_collection_id,
    parse_collection_external_id,
)


class TestCollectionId:
    def test_generate_returns_uuid_string(self) -> None:
        cid = generate_collection_id()
        assert isinstance(cid, str)
        assert len(cid) == 36  # UUID format: 8-4-4-4-12

    def test_format_external_id(self) -> None:
        cid = generate_collection_id()
        external = format_collection_external_id(cid)
        assert external.startswith(f"{COLLECTION_ID_PREFIX}_")

    def test_roundtrip(self) -> None:
        cid = generate_collection_id()
        external = format_collection_external_id(cid)
        parsed = parse_collection_external_id(external)
        assert parsed == cid

    def test_parse_invalid_prefix_raises(self) -> None:
        cid = generate_collection_id()
        external = f"album_{format_collection_external_id(cid).split('_')[1]}"
        with pytest.raises(ValueError, match="collection"):
            parse_collection_external_id(external)
