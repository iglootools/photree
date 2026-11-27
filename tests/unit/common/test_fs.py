from pathlib import Path

import pytest

from photree.common.fs import (
    FileDeletionError,
    delete_files,
    matching_subdirectories,
    partition_subdirectories,
)
from photree.common.fs_output import format_file_deletion_error


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


class TestDeleteFiles:
    def test_failure_reports_the_files_already_deleted(self, tmp_path: Path) -> None:
        (tmp_path / "a.jpg").touch()
        (tmp_path / "c.jpg").touch()

        with pytest.raises(FileDeletionError) as exc_info:
            delete_files(tmp_path, ["a.jpg", "b.jpg", "c.jpg"], dry_run=False)

        assert exc_info.value.deleted == ("a.jpg",)
        assert exc_info.value.failed == "b.jpg"
        assert exc_info.value.remaining == ("c.jpg",)
        assert not (tmp_path / "a.jpg").exists()
        assert (tmp_path / "c.jpg").exists()

    def test_dry_run_deletes_nothing(self, tmp_path: Path) -> None:
        (tmp_path / "a.jpg").touch()

        assert delete_files(tmp_path, ["a.jpg"], dry_run=True) == 1
        assert (tmp_path / "a.jpg").exists()

    def test_error_lists_deleted_and_kept_files_relative_to_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        exc = FileDeletionError(
            tmp_path / "album/main-jpg",
            deleted=("a.jpg",),
            failed="b.jpg",
            remaining=("c.jpg",),
            reason="Permission denied",
        )

        assert format_file_deletion_error(exc, tmp_path).splitlines() == [
            "Could not delete b.jpg from album/main-jpg: Permission denied.",
            "Already deleted from album/main-jpg before it failed:",
            "  a.jpg",
            "Not deleted (still in album/main-jpg):",
            "  b.jpg",
            "  c.jpg",
        ]
