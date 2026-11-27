from pathlib import Path

from typer.testing import Result

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
from tests.fakes import invoke_cli


def _init_collection(
    collection_dir: Path,
    members: CollectionMembers = CollectionMembers.MANUAL,
    lifecycle: CollectionLifecycle = CollectionLifecycle.EXPLICIT,
    strategy: CollectionStrategy = CollectionStrategy.IMPORT,
) -> None:
    save_collection_metadata(
        collection_dir,
        CollectionMetadata(
            id=generate_collection_id(),
            members=members,
            lifecycle=lifecycle,
            strategy=strategy,
        ),
    )


class TestCollectionMetadataSet:
    def test_updates_members(self, tmp_path: Path) -> None:
        _init_collection(tmp_path, members=CollectionMembers.MANUAL)
        result = invoke_cli(
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--members",
                "smart",
                "--strategy",
                "date-range",
            ],
        )
        assert result.exit_code == 0
        assert "members: manual -> smart" in result.output
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.members == CollectionMembers.SMART

    def test_updates_lifecycle_to_implicit_requires_smart(self, tmp_path: Path) -> None:
        """Setting lifecycle=implicit on a manual collection is rejected."""
        _init_collection(tmp_path, lifecycle=CollectionLifecycle.EXPLICIT)
        result = invoke_cli(
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
        assert result.exit_code == 2
        assert "invalid combination" in result.output

    def test_updates_lifecycle_to_implicit_with_smart(self, tmp_path: Path) -> None:
        _init_collection(
            tmp_path,
            members=CollectionMembers.SMART,
            lifecycle=CollectionLifecycle.EXPLICIT,
            strategy=CollectionStrategy.DATE_RANGE,
        )
        result = invoke_cli(
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--lifecycle",
                "implicit",
                "--strategy",
                "album-series",
            ],
        )
        assert result.exit_code == 0
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.lifecycle == CollectionLifecycle.IMPLICIT

    def test_updates_all(self, tmp_path: Path) -> None:
        _init_collection(tmp_path)
        result = invoke_cli(
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--members",
                "smart",
                "--lifecycle",
                "implicit",
                "--strategy",
                "album-series",
            ],
        )
        assert result.exit_code == 0
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.members == CollectionMembers.SMART
        assert loaded.lifecycle == CollectionLifecycle.IMPLICIT
        assert loaded.strategy == CollectionStrategy.ALBUM_SERIES

    def test_no_change_when_same_values(self, tmp_path: Path) -> None:
        _init_collection(tmp_path)
        result = invoke_cli(
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--members",
                "manual",
            ],
        )
        assert result.exit_code == 0
        assert "already up to date" in result.output

    def test_fails_without_init(self, tmp_path: Path) -> None:
        result = invoke_cli(
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--members",
                "smart",
            ],
        )
        assert result.exit_code == 1

    def test_fails_when_no_fields_specified(self, tmp_path: Path) -> None:
        _init_collection(tmp_path)
        result = invoke_cli(["collection", "metadata", "set", "-d", str(tmp_path)])
        assert result.exit_code == 2
        assert "No fields specified" in result.output

    def test_preserves_members(self, tmp_path: Path) -> None:
        """Updating members/lifecycle should not wipe existing members."""
        album_id = "0192d4e1-7c3f-7b4a-8c5e-f6a7b8c9d0e1"
        save_collection_metadata(
            tmp_path,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                albums=[album_id],
            ),
        )
        invoke_cli(
            [
                "collection",
                "metadata",
                "set",
                "-d",
                str(tmp_path),
                "--members",
                "smart",
                "--strategy",
                "date-range",
            ],
        )
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.albums == [album_id]


class TestSwitchToSmartWithMedia:
    def _setup(self, collection_dir: Path) -> None:
        save_collection_metadata(
            collection_dir,
            CollectionMetadata(
                id=generate_collection_id(),
                members=CollectionMembers.MANUAL,
                lifecycle=CollectionLifecycle.EXPLICIT,
                images=["img-1", "img-2"],
                videos=["vid-1"],
            ),
        )

    def _switch(self, collection_dir: Path, *extra: str) -> Result:
        return invoke_cli(
            [
                *("collection", "metadata", "set", "-d", str(collection_dir)),
                *("--members", "smart", "--strategy", "date-range", *extra),
            ],
        )

    def test_refused_without_force(self, tmp_path: Path) -> None:
        self._setup(tmp_path)

        result = self._switch(tmp_path)

        assert result.exit_code == 1
        assert "has 2 image(s) and 1 video(s)" in result.output
        assert "--force" in result.output
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.members == CollectionMembers.MANUAL

    def test_switches_with_force_and_warns(self, tmp_path: Path) -> None:
        self._setup(tmp_path)

        result = self._switch(tmp_path, "--force")

        assert result.exit_code == 0, result.output
        assert "warning:" in result.output
        loaded = load_collection_metadata(tmp_path)
        assert loaded is not None
        assert loaded.members == CollectionMembers.SMART
