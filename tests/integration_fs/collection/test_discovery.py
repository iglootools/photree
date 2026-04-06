"""Tests for collection discovery."""

from __future__ import annotations

from pathlib import Path

from photree.collection.id import generate_collection_id
from photree.collection.store.collection_discovery import (
    discover_collections,
    is_collection,
)
from photree.collection.store.metadata import save_collection_metadata
from photree.collection.store.protocol import (
    CollectionKind,
    CollectionLifecycle,
    CollectionMetadata,
)


def _init_collection(collection_dir: Path) -> None:
    collection_dir.mkdir(parents=True, exist_ok=True)
    save_collection_metadata(
        collection_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            kind=CollectionKind.MANUAL,
            lifecycle=CollectionLifecycle.EXPLICIT,
        ),
    )


class TestIsCollection:
    def test_with_metadata(self, tmp_path: Path) -> None:
        col = tmp_path / "my-collection"
        _init_collection(col)
        assert is_collection(col) is True

    def test_without_metadata(self, tmp_path: Path) -> None:
        col = tmp_path / "not-a-collection"
        col.mkdir()
        assert is_collection(col) is False

    def test_nonexistent(self, tmp_path: Path) -> None:
        assert is_collection(tmp_path / "nope") is False


class TestDiscoverCollections:
    def test_finds_collections(self, tmp_path: Path) -> None:
        _init_collection(tmp_path / "2024" / "col-a")
        _init_collection(tmp_path / "2024" / "col-b")
        (tmp_path / "2024" / "not-a-collection").mkdir(parents=True)

        found = discover_collections(tmp_path)
        names = {p.name for p in found}
        assert names == {"col-a", "col-b"}

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert discover_collections(tmp_path) == []

    def test_nested_collections(self, tmp_path: Path) -> None:
        _init_collection(tmp_path / "2024" / "col-parent")
        # Nested collection inside another is not descended into
        _init_collection(tmp_path / "2024" / "col-parent" / "nested")
        found = discover_collections(tmp_path)
        assert len(found) == 1
        assert found[0].name == "col-parent"
