"""Tests for photree.common.fs directory walking helpers."""

from pathlib import Path

from photree.common.fs import partition_subdirectories


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
            tmp_path, lambda p: p.name.startswith("album")
        )

        assert sorted(matched) == [tmp_path / "a/album-1", tmp_path / "a/album-2"]
        assert sorted(skipped) == [tmp_path / "a", tmp_path / "b", tmp_path / "b/leaf"]

    def test_base_dir_never_returned(self, tmp_path: Path) -> None:
        matched, skipped = partition_subdirectories(tmp_path, lambda _p: True)
        assert (matched, skipped) == ([], [])
