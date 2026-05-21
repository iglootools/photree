"""Tests for ``photree collection init`` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from photree.cli import app
from photree.collection.id import generate_collection_id
from photree.collection.store.metadata import (
    load_collection_metadata,
    save_collection_metadata,
)
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
)

runner = CliRunner()


class TestCollectionInit:
    def test_creates_collection_yaml(self, tmp_path: Path) -> None:
        col = tmp_path / "my-collection"
        col.mkdir()
        result = runner.invoke(app, ["collection", "init", "-d", str(col)])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "Collection ID:" in result.output
        assert load_collection_metadata(col) is not None

    def test_defaults_to_manual_explicit(self, tmp_path: Path) -> None:
        col = tmp_path / "my-collection"
        col.mkdir()
        runner.invoke(app, ["collection", "init", "-d", str(col)])
        metadata = load_collection_metadata(col)
        assert metadata is not None
        assert metadata.members == CollectionMembers.MANUAL
        assert metadata.lifecycle == CollectionLifecycle.EXPLICIT

    def test_custom_members_and_lifecycle(self, tmp_path: Path) -> None:
        col = tmp_path / "my-collection"
        col.mkdir()
        result = runner.invoke(
            app,
            [
                "collection",
                "init",
                "-d",
                str(col),
                "--members",
                "smart",
                "--lifecycle",
                "implicit",
                "--strategy",
                "album-series",
            ],
        )
        assert result.exit_code == 0
        metadata = load_collection_metadata(col)
        assert metadata is not None
        assert metadata.members == CollectionMembers.SMART
        assert metadata.lifecycle == CollectionLifecycle.IMPLICIT
        assert metadata.strategy == CollectionStrategy.ALBUM_SERIES

    def test_rejects_implicit_manual(self, tmp_path: Path) -> None:
        col = tmp_path / "my-collection"
        col.mkdir()
        result = runner.invoke(
            app,
            [
                "collection",
                "init",
                "-d",
                str(col),
                "--members",
                "manual",
                "--lifecycle",
                "implicit",
            ],
        )
        assert result.exit_code == 1
        assert "invalid combination" in result.output

    def test_fails_if_already_initialized(self, tmp_path: Path) -> None:
        col = tmp_path / "my-collection"
        col.mkdir()
        save_collection_metadata(
            col,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
            ),
        )
        result = runner.invoke(app, ["collection", "init", "-d", str(col)])
        assert result.exit_code == 1
        assert "already initialized" in result.output

    def test_does_not_overwrite_existing_id(self, tmp_path: Path) -> None:
        col = tmp_path / "my-collection"
        col.mkdir()
        original_id = generate_collection_id()
        save_collection_metadata(
            col,
            CollectionMetadata(
                id=original_id,
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
            ),
        )
        runner.invoke(app, ["collection", "init", "-d", str(col)])
        metadata = load_collection_metadata(col)
        assert metadata is not None
        assert metadata.id == original_id
