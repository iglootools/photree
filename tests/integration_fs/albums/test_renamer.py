"""Tests for executing planned album renames."""

from __future__ import annotations

from pathlib import Path

import pytest

from photree.albums.renamer import (
    RenameAction,
    RenameCollisionError,
    RenamePhase,
    check_rename_collisions,
    execute_renames,
)


def _album(parent: Path, name: str) -> Path:
    path = parent / name
    path.mkdir(parents=True)
    (path / "marker.txt").write_text(name, encoding="utf-8")
    return path


def _action(path: Path, new_name: str) -> RenameAction:
    return RenameAction(album_path=path, current_name=path.name, new_name=new_name)


def _marker(path: Path) -> str:
    return (path / "marker.txt").read_text(encoding="utf-8")


class TestExecuteRenames:
    def test_swap(self, tmp_path: Path) -> None:
        # Regression: renaming in place hit "directory not empty" on the
        # first move, after collision checks had passed.
        a = _album(tmp_path, "2024-01-01 - A")
        b = _album(tmp_path, "2024-01-01 - B")
        actions = (_action(a, b.name), _action(b, a.name))
        check_rename_collisions(actions)

        result = execute_renames(actions)

        assert result.failure is None
        assert result.renamed == 2
        assert _marker(tmp_path / "2024-01-01 - A") == "2024-01-01 - B"
        assert _marker(tmp_path / "2024-01-01 - B") == "2024-01-01 - A"

    def test_chain(self, tmp_path: Path) -> None:
        a = _album(tmp_path, "2024-01-01 - A")
        b = _album(tmp_path, "2024-01-01 - B")
        actions = (_action(a, "2024-01-01 - B"), _action(b, "2024-01-01 - C"))
        check_rename_collisions(actions)

        result = execute_renames(actions)

        assert result.failure is None
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "2024-01-01 - B",
            "2024-01-01 - C",
        ]
        assert _marker(tmp_path / "2024-01-01 - B") == "2024-01-01 - A"
        assert _marker(tmp_path / "2024-01-01 - C") == "2024-01-01 - B"

    def test_failure_rolls_back_and_reports(self, tmp_path: Path) -> None:
        a = _album(tmp_path, "2024-01-01 - A")
        b = _album(tmp_path, "2024-01-01 - B")
        # An occupied, non-empty target the collision check was not told about
        # (e.g. created concurrently): the final move of B fails.
        _album(tmp_path, "2024-01-01 - Taken")
        actions = (_action(a, "2024-01-01 - A2"), _action(b, "2024-01-01 - Taken"))

        result = execute_renames(actions)

        assert result.renamed == 0
        assert result.failure is not None
        assert result.failure.phase == RenamePhase.FINALIZE
        assert result.failure.action == actions[1]
        assert result.failure.stranded == ()
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "2024-01-01 - A",
            "2024-01-01 - B",
            "2024-01-01 - Taken",
        ]


class TestCheckRenameCollisions:
    def test_existing_unrelated_target_collides(self, tmp_path: Path) -> None:
        a = _album(tmp_path, "2024-01-01 - A")
        _album(tmp_path, "2024-01-01 - B")
        with pytest.raises(RenameCollisionError):
            check_rename_collisions((_action(a, "2024-01-01 - B"),))

    def test_two_renames_to_same_target_collide(self, tmp_path: Path) -> None:
        a = _album(tmp_path, "2024-01-01 - A")
        b = _album(tmp_path, "2024-01-01 - B")
        with pytest.raises(RenameCollisionError):
            check_rename_collisions(
                (_action(a, "2024-01-01 - C"), _action(b, "2024-01-01 - C"))
            )
