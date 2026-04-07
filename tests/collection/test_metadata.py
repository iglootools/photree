"""Tests for collection metadata I/O."""

from __future__ import annotations

from pathlib import Path

from photree.collection.id import generate_collection_id
from photree.collection.store.metadata import (
    load_collection_metadata,
    save_collection_metadata,
)
from photree.collection.store.protocol import (
    COLLECTION_YAML,
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)
from photree.fsprotocol import PHOTREE_DIR


class TestCollectionMetadata:
    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        collection_dir = tmp_path / "my-collection"
        collection_dir.mkdir()
        metadata = CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        )
        save_collection_metadata(collection_dir, metadata)
        loaded = load_collection_metadata(collection_dir)
        assert loaded is not None
        assert loaded.id == metadata.id
        assert loaded.members == CollectionMembers.MANUAL
        assert loaded.lifecycle == CollectionLifecycle.EXPLICIT

    def test_load_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert load_collection_metadata(tmp_path) is None

    def test_members_default_to_empty(self, tmp_path: Path) -> None:
        collection_dir = tmp_path / "col"
        collection_dir.mkdir()
        metadata = CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.SMART,
            lifecycle=CollectionLifecycle.IMPLICIT,
            strategy=CollectionStrategy.ALBUM_SERIES,
        )
        save_collection_metadata(collection_dir, metadata)
        loaded = load_collection_metadata(collection_dir)
        assert loaded is not None
        assert loaded.albums == []
        assert loaded.collections == []
        assert loaded.images == []
        assert loaded.videos == []

    def test_members_persisted(self, tmp_path: Path) -> None:
        collection_dir = tmp_path / "col"
        collection_dir.mkdir()
        album_id = "0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1"
        image_id = "0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e2"
        metadata = CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
            albums=[album_id],
            images=[image_id],
        )
        save_collection_metadata(collection_dir, metadata)
        loaded = load_collection_metadata(collection_dir)
        assert loaded is not None
        assert loaded.albums == [album_id]
        assert loaded.images == [image_id]
        assert loaded.collections == []
        assert loaded.videos == []

    def test_creates_photree_dir(self, tmp_path: Path) -> None:
        collection_dir = tmp_path / "col"
        collection_dir.mkdir()
        metadata = CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        )
        save_collection_metadata(collection_dir, metadata)
        assert (collection_dir / PHOTREE_DIR / COLLECTION_YAML).is_file()

    def test_kebab_case_yaml_keys(self, tmp_path: Path) -> None:
        """Verify YAML uses kebab-case keys (not snake_case)."""
        collection_dir = tmp_path / "col"
        collection_dir.mkdir()
        metadata = CollectionMetadata(
            id=generate_collection_id(),
            members=CollectionMembers.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        )
        save_collection_metadata(collection_dir, metadata)
        content = (collection_dir / PHOTREE_DIR / COLLECTION_YAML).read_text()
        assert "members:" in content
        assert "lifecycle:" in content
        assert "strategy:" in content
        # No underscores in keys
        assert "collection_" not in content
