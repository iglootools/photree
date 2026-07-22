"""Tests for photree.album.importer.tasks discovery."""

from __future__ import annotations

from pathlib import Path

from photree.album.importer.tasks import (
    discover_import_tasks,
    has_import_tasks,
)
from photree.album.store.protocol import (
    ios_import_csv,
    ios_import_dir,
    std_import_dir,
)


class TestDiscoverImportTasks:
    def test_empty_album(self, tmp_path: Path) -> None:
        assert discover_import_tasks(tmp_path) == []
        assert has_import_tasks(tmp_path) is False

    def test_ios_dir_only(self, tmp_path: Path) -> None:
        (tmp_path / ios_import_dir("main")).mkdir()
        tasks = discover_import_tasks(tmp_path)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.is_ios
        assert task.name == "main"
        assert task.selection_dir == tmp_path / ios_import_dir("main")
        assert task.selection_csv is None

    def test_ios_csv_only(self, tmp_path: Path) -> None:
        (tmp_path / ios_import_csv("main")).write_text("IMG_0001.HEIC\n")
        tasks = discover_import_tasks(tmp_path)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.is_ios
        assert task.selection_dir is None
        assert task.selection_csv == tmp_path / ios_import_csv("main")

    def test_ios_dir_and_csv_merge_into_one_task(self, tmp_path: Path) -> None:
        (tmp_path / ios_import_dir("main")).mkdir()
        (tmp_path / ios_import_csv("main")).write_text("IMG_0001.HEIC\n")
        tasks = discover_import_tasks(tmp_path)
        assert len(tasks) == 1
        assert tasks[0].selection_dir is not None
        assert tasks[0].selection_csv is not None

    def test_std_dir(self, tmp_path: Path) -> None:
        (tmp_path / std_import_dir("nelu")).mkdir()
        tasks = discover_import_tasks(tmp_path)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.is_std
        assert task.name == "nelu"
        assert task.staging_dir == tmp_path / std_import_dir("nelu")

    def test_multiple_sources_sorted_main_first(self, tmp_path: Path) -> None:
        (tmp_path / std_import_dir("nelu")).mkdir()
        (tmp_path / ios_import_dir("bruno")).mkdir()
        (tmp_path / ios_import_dir("main")).mkdir()
        tasks = discover_import_tasks(tmp_path)
        assert [t.name for t in tasks] == ["main", "bruno", "nelu"]

    def test_ios_and_std_same_name_coexist(self, tmp_path: Path) -> None:
        (tmp_path / ios_import_dir("main")).mkdir()
        (tmp_path / std_import_dir("main")).mkdir()
        tasks = discover_import_tasks(tmp_path)
        assert len(tasks) == 2
        assert {(t.name, t.is_ios) for t in tasks} == {("main", True), ("main", False)}
