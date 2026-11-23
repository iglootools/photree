from pathlib import Path

from photree.common.fs import matching_subdirectories, partition_subdirectories


def _mkdirs(base: Path, *names: str) -> None:
    for name in names:
        (base / name).mkdir(parents=True, exist_ok=True)


class TestPartitionSubdirectories:
    def test_missing_base_dir(self, tmp_path: Path) -> None:
        assert partition_subdirectories(tmp_path / "nope", lambda _p: True) == (
            [],
            [],
        )

    def test_matches_stop_descent_and_parents_are_skipped(self, tmp_path: Path) -> None:
        _mkdirs(tmp_path, "a/album-1/inner-album", "a/album-2", "b/leaf", ".hidden")

        matched, skipped = partition_subdirectories(
            tmp_path,
            lambda p: p.name.startswith("album"),
        )

        assert sorted(matched) == [tmp_path / "a/album-1", tmp_path / "a/album-2"]
        assert sorted(skipped) == [tmp_path / "a", tmp_path / "b", tmp_path / "b/leaf"]

    def test_base_dir_never_returned(self, tmp_path: Path) -> None:
        matched, skipped = partition_subdirectories(tmp_path, lambda _p: True)
        assert (matched, skipped) == ([], [])


class TestMatchingSubdirectories:
    def test_missing_base_dir(self, tmp_path: Path) -> None:
        assert matching_subdirectories(tmp_path / "nope", lambda _p: True) == []

    def test_matches_stop_descent_and_hidden_dirs_are_ignored(
        self,
        tmp_path: Path,
    ) -> None:
        _mkdirs(tmp_path, "a/album-1/album-inner", "a/album-2", ".hidden/album-3")

        assert matching_subdirectories(
            tmp_path,
            lambda p: p.name.startswith("album"),
        ) == [tmp_path / "a/album-1", tmp_path / "a/album-2"]

    def test_base_dir_never_returned_when_it_matches(self, tmp_path: Path) -> None:
        """Regression: a matching base_dir was returned, contrary to the contract."""
        _mkdirs(tmp_path, "child")

        assert matching_subdirectories(tmp_path, lambda _p: True) == [
            tmp_path / "child",
        ]
