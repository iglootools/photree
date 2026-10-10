"""``albums rename-from-csv`` / ``gallery rename-from-csv`` wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import typer

from ....clihelpers.console import err_console
from ....common.formatting import indent
from ....common.fs import display_path
from ...cmd_handler.rename import BatchRenameResult, batch_rename_from_csv
from ...renamer import (
    RenameCollisionError,
    RenameFailure,
    RenamePhase,
    RenamePlanError,
    RenamePlanErrorKind,
)


def format_rename_plan_error(error: RenamePlanError) -> str:
    """One line describing an invalid CSV row."""
    match error.kind:
        case RenamePlanErrorKind.EMPTY_ID:
            reason = "empty album ID"
        case RenamePlanErrorKind.INVALID_ID:
            reason = f"invalid album ID format: {error.external_id}"
        case RenamePlanErrorKind.ID_NOT_FOUND:
            reason = f"album ID not found: {error.external_id}"
        case RenamePlanErrorKind.UNPARSEABLE_NAME:
            reason = f"cannot parse current album name: {error.album_name}"
        case RenamePlanErrorKind.EMPTY_TITLE:
            reason = f"{error.external_id}: title is required but empty"
    return f"row {error.row}: {reason}"


def format_rename_failure(failure: RenameFailure, cwd: Path) -> str:
    """Describe a failed rename run, listing anything left out of place."""
    action = failure.action
    what = {
        RenamePhase.PREFLIGHT: "preparing to rename",
        RenamePhase.STAGE: "moving aside",
        RenamePhase.FINALIZE: "renaming",
    }[failure.phase]
    header = (
        f"Rename failed while {what} {display_path(action.album_path, cwd)} "
        f"→ {action.new_name}: {failure.reason}"
    )
    stranded = (
        [
            "These directories could not be restored; rename them back by hand:",
            *(indent(str(display_path(p, cwd))) for p in failure.stranded),
        ]
        if failure.stranded
        else ["All renames were rolled back. Nothing was changed."]
    )
    return "\n".join([header, *stranded])


def _print_plan(result: BatchRenameResult, cwd: Path) -> None:
    typer.echo(f"{result.row_count} row(s) in CSV, {len(result.actions)} change(s).\n")
    for action in result.actions:
        typer.echo(
            indent(f"{display_path(action.album_path, cwd)}\n→ {action.new_name}")
        )
        typer.echo()


def run_batch_rename_from_csv(
    index: Mapping[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Shared implementation for gallery rename-from-csv / albums rename-from-csv."""
    cwd = Path.cwd()

    try:
        result = batch_rename_from_csv(index, csv_file, dry_run=dry_run)
    except RenameCollisionError as exc:
        err_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc

    if result.errors:
        err_console.print(
            "\n".join(indent(format_rename_plan_error(e)) for e in result.errors),
            markup=False,
        )
        err_console.print(f"Fix the rows in {display_path(csv_file, cwd)} and re-run.")
        raise typer.Exit(code=1)

    if not result.actions:
        typer.echo(
            "CSV is empty. Nothing to rename."
            if result.row_count == 0
            else f"{result.row_count} row(s) in CSV. Nothing to rename."
        )
        raise typer.Exit(code=0)

    _print_plan(result, cwd)
    if result.failure is not None:
        err_console.print(format_rename_failure(result.failure, cwd), markup=False)
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo(f"[dry run] {len(result.actions)} album(s) would be renamed.")
    else:
        typer.echo(f"Renamed {result.renamed} album(s).")
