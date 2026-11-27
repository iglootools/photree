"""The ``photree gallery rename-from-csv`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.albums.batchcli.rename import run_batch_rename_from_csv
from photree.albums.output import format_duplicate_ids_report
from photree.clihelpers.console import err_console
from photree.clihelpers.options import DRY_RUN_OPTION, GALLERY_DIR_OPTION
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.gallery.cli.app import app
from photree.gallery.cli.index_ops import build_index_or_exit


@app.command("rename-from-csv")
def rename_from_csv_cmd(
    ctx: typer.Context,
    csv_file: Annotated[
        Path,
        typer.Argument(
            help=(
                "CSV with desired album state (from list-albums --output csv, edited)."
            ),
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    gallery_dir: GALLERY_DIR_OPTION = None,
    *,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """
    Rename albums from a CSV file (from list-albums --output csv, edited).

    Uses the album ID to look up each album in the gallery, then compares the
    current series, title, and location against the CSV values. Only albums
    where a mutable field changed are renamed. Immutable fields (date, part,
    tags) are preserved from the current on-disk album name.

    The CSV needs the id, series, title and location columns; other columns
    are ignored. A missing column, an album ID on more than one row, or a
    field that would not read back from the new name (one holding '/', ' - ',
    ' @ ' or a '[tag]') stops the run before anything is renamed.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    resolved = resolve_gallery_or_exit(gallery_dir, cwd=cwd)

    index = build_index_or_exit(resolved, cwd)

    if index.duplicates:
        err_console.print(
            format_duplicate_ids_report(index.duplicates, cwd),
            markup=False,
        )
        raise typer.Exit(code=1)

    run_batch_rename_from_csv(index.id_to_path, csv_file, dry_run=dry_run, cwd=cwd)
