"""Batch album renaming from a CSV file."""

import csv as csv_mod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from photree.albums.renamer import (
    RenameAction,
    RenameCsvFormatError,
    RenameCsvFormatErrorKind,
    RenameFailure,
    RenamePlanError,
    check_rename_collisions,
    execute_renames,
    plan_renames_from_csv,
    validate_rename_csv_columns,
)


@dataclass(frozen=True)
class BatchRenameResult:
    """
    Result of batch album renaming.

    ``failure`` is set when executing the renames failed part-way (the run is
    rolled back as far as possible; see :class:`RenameFailure`).
    """

    row_count: int
    actions: tuple[RenameAction, ...]
    errors: tuple[RenamePlanError, ...]
    renamed: int
    failure: RenameFailure | None = None


def _read_csv(csv_file: Path) -> tuple[list[dict[str, str]], Sequence[str] | None]:
    """
    Return the CSV's rows and header, the header ``None`` for an empty file.

    Raises :class:`RenameCsvFormatError` when the file is not UTF-8 or the
    CSV parser rejects it.
    """
    try:
        # utf-8-sig: a spreadsheet that saves the CSV with a byte order mark
        # would otherwise turn the first column into "\ufeffid".
        with csv_file.open(encoding="utf-8-sig", newline="") as f:
            reader = csv_mod.DictReader(f)
            try:
                return list(reader), reader.fieldnames
            except csv_mod.Error as exc:
                # The inner reader's count: DictReader updates its own only
                # after a row parses, so it names the line before the bad one.
                raise RenameCsvFormatError(
                    RenameCsvFormatErrorKind.MALFORMED,
                    line=reader.reader.line_num,
                    reason=str(exc),
                ) from exc
    except UnicodeDecodeError as exc:
        raise RenameCsvFormatError(RenameCsvFormatErrorKind.NOT_UTF8) from exc


def batch_rename_from_csv(
    index: Mapping[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
) -> BatchRenameResult:
    """
    Plan and execute album renames from a CSV file.

    Raises :class:`RenameCsvFormatError` when the file is not UTF-8 or not
    valid CSV, :class:`RenameCsvColumnsError` when the CSV lacks a column a
    rename needs, and :class:`RenameCollisionError` when renames would collide.
    """
    rows, fieldnames = _read_csv(csv_file)
    validate_rename_csv_columns(fieldnames)

    actions, errors = plan_renames_from_csv(rows, index)
    if errors or not actions:
        return BatchRenameResult(
            row_count=len(rows),
            actions=(),
            errors=errors,
            renamed=0,
        )

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
