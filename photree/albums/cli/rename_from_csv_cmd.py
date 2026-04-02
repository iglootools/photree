"""``photree albums rename-from-csv`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import AlbumDirOption, DirOption, albums_app
from ...album.id import format_album_external_id
from ...common.fs import display_path
from ...clihelpers.options import DRY_RUN_OPTION
from .batch_ops import resolve_check_batch_albums, run_batch_rename_from_csv


@albums_app.command("rename-from-csv")
def rename_from_csv_cmd(
    csv_file: Annotated[
        Path,
        typer.Argument(
            help="CSV with desired album state (from list --format csv, edited).",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Rename albums from a CSV file (from list --format csv, edited).

    Uses the album ID to look up each album, then compares the
    current series, title, and location against the CSV values. Only albums
    where a mutable field changed are renamed. Immutable fields (date, part,
    tags) are preserved from the current on-disk album name.
    """
    from ..index import MissingAlbumIdError, build_album_index
    from ...clihelpers.console import err_console

    cwd = Path.cwd()
    albums, _ = resolve_check_batch_albums(base_dir, album_dirs)

    # Build album index
    try:
        index = build_album_index(albums)
    except MissingAlbumIdError as exc:
        err_console.print("Albums with missing IDs found:")
        for p in exc.albums:
            err_console.print(f"  {display_path(p, cwd)}")
        err_console.print(
            "\nRun 'photree albums fix --id' to generate missing album IDs."
        )
        raise typer.Exit(code=1) from exc

    # Check for duplicate IDs
    if index.duplicates:
        err_console.print("Cannot rename — duplicate album IDs found:")
        for aid, paths in index.duplicates.items():
            err_console.print(f"  {format_album_external_id(aid)}:")
            for p in paths:
                err_console.print(f"    {display_path(p, cwd)}")
        err_console.print(
            "\nResolve duplicates first with 'photree albums fix --new-id'."
        )
        raise typer.Exit(code=1)

    run_batch_rename_from_csv(index.id_to_path, csv_file, dry_run=dry_run)
