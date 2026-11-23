"""``albums rename-from-csv`` / ``gallery rename-from-csv`` wrapper."""

from collections.abc import Mapping
from pathlib import Path

import typer

from photree.albums.cmd_handler.rename import BatchRenameResult, batch_rename_from_csv
from photree.albums.renamer import (
    RENAME_CSV_COLUMNS,
    RenameCollisionError,
    RenameCsvColumnsError,
    RenameFailure,
    RenamePhase,
    RenamePlanError,
    RenamePlanErrorKind,
)
from photree.clihelpers.console import err_console
from photree.common.formatting import format_dry_run, indent
from photree.common.fs import display_path


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
        case RenamePlanErrorKind.DUPLICATE_ID:
            reason = f"album ID appears on more than one row: {error.external_id}"
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


def format_rename_csv_columns_error(
    error: RenameCsvColumnsError,
    csv_file: Path,
    cwd: Path,
) -> str:
    """Describe a rename CSV whose header lacks required columns, and the fix."""
    missing = ", ".join(error.missing)
    return "\n".join(
        [
            f"{display_path(csv_file, cwd)} has no {missing} column(s).",
            f"Add them (the CSV needs {', '.join(RENAME_CSV_COLUMNS)}) and re-run.",
        ],
    )


def _print_plan(result: BatchRenameResult, cwd: Path) -> None:
    typer.echo(f"{result.row_count} row(s) in CSV, {len(result.actions)} change(s).\n")
    for action in result.actions:
        typer.echo(
            indent(f"{display_path(action.album_path, cwd)}\n→ {action.new_name}"),
        )
        typer.echo()


def run_batch_rename_from_csv(
    index: Mapping[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
    cwd: Path,
) -> None:
    """Shared implementation for gallery rename-from-csv / albums rename-from-csv."""
    try:
        result = batch_rename_from_csv(index, csv_file, dry_run=dry_run)
    except RenameCsvColumnsError as exc:
        err_console.print(
            format_rename_csv_columns_error(exc, csv_file, cwd),
            markup=False,
        )
        raise typer.Exit(code=1) from exc
    except RenameCollisionError as exc:
        err_console.print(str(exc), markup=False)
        raise typer.Exit(code=1) from exc

    if result.errors:
        err_console.print(
            "\n".join(indent(format_rename_plan_error(e)) for e in result.errors),
            markup=False,
        )
        err_console.print(
            f"Fix the rows in {display_path(csv_file, cwd)} and re-run.",
            markup=False,
        )
        raise typer.Exit(code=1)

    if not result.actions:
        typer.echo(
            "CSV is empty. Nothing to rename."
            if result.row_count == 0
            else f"{result.row_count} row(s) in CSV. Nothing to rename.",
        )
        raise typer.Exit(code=0)

    _print_plan(result, cwd)
    if result.failure is not None:
        err_console.print(format_rename_failure(result.failure, cwd), markup=False)
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo(
            format_dry_run(
                f"{len(result.actions)} album(s) would be renamed.",
                dry_run=True,
            ),
        )
    else:
        typer.echo(f"Renamed {result.renamed} album(s).")
