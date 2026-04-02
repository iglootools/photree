"""Batch rename command handler."""

from __future__ import annotations

import csv as csv_mod
from dataclasses import dataclass
from pathlib import Path

from ...gallery import plan_renames_from_csv
from ...gallery.batch_rename import (
    RenameAction,
    check_rename_collisions,
    execute_renames,
)


@dataclass(frozen=True)
class BatchRenameResult:
    """Result of batch album renaming."""

    row_count: int
    actions: tuple[RenameAction, ...]
    errors: tuple[str, ...]
    renamed: int


def batch_rename_from_csv(
    index: dict[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
) -> BatchRenameResult:
    """Plan and execute album renames from a CSV file.

    Raises :class:`RenameCollisionError` when renames would collide.
    """
    with open(csv_file, encoding="utf-8") as f:
        rows = list(csv_mod.DictReader(f))

    if not rows:
        return BatchRenameResult(row_count=0, actions=(), errors=(), renamed=0)

    actions, errors = plan_renames_from_csv(rows, index)

    if errors:
        return BatchRenameResult(
            row_count=len(rows), actions=(), errors=errors, renamed=0
        )

    if not actions:
        return BatchRenameResult(row_count=len(rows), actions=(), errors=(), renamed=0)

    # Raises RenameCollisionError on collision
    check_rename_collisions(actions)

    renamed = 0 if dry_run else execute_renames(actions)

    return BatchRenameResult(
        row_count=len(rows),
        actions=actions,
        errors=(),
        renamed=renamed,
    )
