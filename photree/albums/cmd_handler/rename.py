"""Batch rename command handler."""

from __future__ import annotations

import csv as csv_mod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..renamer import (
    RenameAction,
    RenameFailure,
    RenamePlanError,
    check_rename_collisions,
    execute_renames,
    plan_renames_from_csv,
)


@dataclass(frozen=True)
class BatchRenameResult:
    """Result of batch album renaming.

    ``failure`` is set when executing the renames failed part-way (the run is
    rolled back as far as possible; see :class:`RenameFailure`).
    """

    row_count: int
    actions: tuple[RenameAction, ...]
    errors: tuple[RenamePlanError, ...]
    renamed: int
    failure: RenameFailure | None = None


def batch_rename_from_csv(
    index: Mapping[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
) -> BatchRenameResult:
    """Plan and execute album renames from a CSV file.

    Raises :class:`RenameCollisionError` when renames would collide.
    """
    with open(csv_file, encoding="utf-8", newline="") as f:
        rows = list(csv_mod.DictReader(f))

    actions, errors = plan_renames_from_csv(rows, index)
    if errors or not actions:
        return BatchRenameResult(
            row_count=len(rows), actions=(), errors=errors, renamed=0
        )

    # Raises RenameCollisionError on collision
    check_rename_collisions(actions)
    if dry_run:
        return BatchRenameResult(len(rows), actions, errors=(), renamed=0)

    execution = execute_renames(actions)
    return BatchRenameResult(
        row_count=len(rows),
        actions=actions,
        errors=(),
        renamed=execution.renamed,
        failure=execution.failure,
    )
