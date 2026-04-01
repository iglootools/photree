"""``photree gallery rename-from-csv`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clicommons.console import err_console
from ...fs import display_path, format_album_external_id
from ...albums.cli.batch_ops import run_batch_rename_from_csv
from .ops import build_index_or_exit, resolve_gallery_or_exit


@gallery_app.command("rename-from-csv")
def rename_from_csv_cmd(
    csv_file: Annotated[
        Path,
        typer.Argument(
            help="CSV with desired album state (from list-albums --format csv, edited).",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show what would be renamed without making changes.",
        ),
    ] = False,
) -> None:
    """Rename albums from a CSV file (from list-albums --format csv, edited).

    Uses the album ID to look up each album in the gallery, then compares the
    current series, title, and location against the CSV values. Only albums
    where a mutable field changed are renamed. Immutable fields (date, part,
    tags) are preserved from the current on-disk album name.
    """
    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()

    # Build album index
    index = build_index_or_exit(resolved, cwd)

    # Check for duplicate IDs in gallery
    if index.duplicates:
        err_console.print("Cannot rename — duplicate album IDs in gallery:")
        for aid, paths in index.duplicates.items():
            err_console.print(f"  {format_album_external_id(aid)}:")
            for p in paths:
                err_console.print(f"    {display_path(p, cwd)}")
        err_console.print(
            "\nResolve duplicates first with 'photree gallery fix --new-id'."
        )
        raise typer.Exit(code=1)

    run_batch_rename_from_csv(index.id_to_path, csv_file, dry_run=dry_run)
