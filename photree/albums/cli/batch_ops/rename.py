"""``albums rename-from-csv`` / ``gallery rename-from-csv`` wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ....clihelpers.console import err_console
from ....common.fs import display_path
from ...cmd_handler.rename import batch_rename_from_csv


def run_batch_rename_from_csv(
    index: dict[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Shared implementation for gallery rename-from-csv / albums rename-from-csv."""
    from ...renamer import RenameCollisionError

    cwd = Path.cwd()

    try:
        result = batch_rename_from_csv(index, csv_file, dry_run=dry_run)
    except RenameCollisionError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc

    if result.errors:
        for err in result.errors:
            err_console.print(f"  {err}")
        raise typer.Exit(code=1)

    if not result.actions:
        if result.row_count == 0:
            typer.echo("CSV is empty. Nothing to rename.")
        else:
            typer.echo(f"{result.row_count} row(s) in CSV. Nothing to rename.")
        raise typer.Exit(code=0)

    # Display plan
    typer.echo(f"{result.row_count} row(s) in CSV, {len(result.actions)} change(s).\n")

    for action in result.actions:
        typer.echo(f"  {display_path(action.album_path, cwd)}")
        typer.echo(f"  \u2192 {action.new_name}")
        typer.echo()

    if dry_run:
        typer.echo(f"[dry run] {len(result.actions)} album(s) would be renamed.")
    else:
        typer.echo(f"Renamed {result.renamed} album(s).")
