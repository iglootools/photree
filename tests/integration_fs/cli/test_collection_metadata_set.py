"""Tests for ``photree collection metadata set`` command."""

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
    CollectionKind,
    CollectionLifecycle,
    CollectionMetadata,
)

runner = CliRunner()


def _init_collection(
    collection_dir: Path,
    kind: CollectionKind = CollectionKind.MANUAL,
    lifecycle: CollectionLifecycle = CollectionLifecycle.EXPLICIT,
) -> None:
    save_collection_metadata(
        collection_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            kind=kind,
            lifecycle=lifecycle,
        ),
    )


class TestCollectionMetadataSet:
    def test_updates_kind(self, tmp_path: Path) -> None:
        _init_collection(tmp_path, kind=CollectionKind.MANUAL)
        result = runner.invoke(
            app,
            ["collection", "metadata", "set", "-d", str(tmp_path), "--kind", "smart"],
        )
        assert result.exit_code == 0
        assert "kind: manual -> smart" in result.output
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.kind == CollectionKind.SMART

    def test_updates_lifecycle_to_implicit_requires_smart(self, tmp_path: Path) -> None:
        """Setting lifecycle=implicit on a manual collection is rejected."""
        _init_collection(tmp_path, lifecycle=CollectionLifecycle.EXPLICIT)
        result = runner.invoke(
            app,
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--lifecycle",
                "implicit",
            ],
        )
        assert result.exit_code == 1
        assert "implicit" in result.output

    def test_updates_lifecycle_to_implicit_with_smart(self, tmp_path: Path) -> None:
        _init_collection(
            tmp_path,
            kind=CollectionKind.SMART,
            lifecycle=CollectionLifecycle.EXPLICIT,
        )
        result = runner.invoke(
            app,
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--lifecycle",
                "implicit",
            ],
        )
        assert result.exit_code == 0
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.lifecycle == CollectionLifecycle.IMPLICIT

    def test_updates_both(self, tmp_path: Path) -> None:
        _init_collection(tmp_path)
        result = runner.invoke(
            app,
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--kind",
                "smart",
                "--lifecycle",
                "implicit",
            ],
        )
        assert result.exit_code == 0
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.kind == CollectionKind.SMART
        assert loaded.lifecycle == CollectionLifecycle.IMPLICIT

    def test_no_change_when_same_values(self, tmp_path: Path) -> None:
        _init_collection(tmp_path)
        result = runner.invoke(
            app,
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--kind",
                "manual",
            ],
        )
        assert result.exit_code == 0
        assert "already up to date" in result.output

    def test_fails_without_init(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--kind",
                "smart",
            ],
        )
        assert result.exit_code == 1

    def test_fails_when_no_fields_specified(self, tmp_path: Path) -> None:
        _init_collection(tmp_path)
        result = runner.invoke(
            app,
            ["collection", "metadata", "set", "-d", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "No fields specified" in result.output

    def test_preserves_members(self, tmp_path: Path) -> None:
        """Updating kind/lifecycle should not wipe existing members."""
        album_id = "0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1"
        save_collection_metadata(
            tmp_path,
            CollectionMetadata(
                id=generate_collection_id(),
                kind=CollectionKind.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                albums=[album_id],
            ),
        )
        runner.invoke(
            app,
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--kind",
                "smart",
            ],
        )
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.albums == [album_id]
