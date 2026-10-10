"""``photree albums rename-from-csv`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...album.id import format_album_external_id
from ...clihelpers.console import err_console
from ...clihelpers.options import DRY_RUN_OPTION
from ...common.formatting import indent
from ...common.fs import display_path
from ..index import AlbumIndex, MissingAlbumIdError, build_album_index
from . import AlbumDirOption, DirOption, albums_app
from .batch_ops.rename import run_batch_rename_from_csv
from .ops import resolve_check_batch_albums


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
    albums, _ = resolve_check_batch_albums(base_dir, album_dirs)
    index = _build_index_or_exit(albums, Path.cwd())
    run_batch_rename_from_csv(index.id_to_path, csv_file, dry_run=dry_run)


def _build_index_or_exit(albums: list[Path], cwd: Path) -> AlbumIndex:
    """Index albums by ID, exiting with a fix suggestion on missing/duplicate IDs."""
    try:
        index = build_album_index(albums)
    except MissingAlbumIdError as exc:
        err_console.print(_missing_ids_report(exc.albums, cwd), markup=False)
        raise typer.Exit(code=1) from exc
    if index.duplicates:
        err_console.print(_duplicate_ids_report(index, cwd), markup=False)
        raise typer.Exit(code=1)
    return index


def _missing_ids_report(albums: tuple[Path, ...], cwd: Path) -> str:
    return "\n".join(
        [
            "Albums with missing IDs found:",
            *(indent(str(display_path(p, cwd))) for p in albums),
            "\nRun 'photree albums fix --id' to generate missing album IDs.",
        ]
    )


def _duplicate_ids_report(index: AlbumIndex, cwd: Path) -> str:
    return "\n".join(
        [
            "Cannot rename — duplicate album IDs found:",
            *(
                line
                for aid, paths in index.duplicates.items()
                for line in [
                    indent(f"{format_album_external_id(aid)}:"),
                    *(indent(str(display_path(p, cwd)), 2) for p in paths),
                ]
            ),
            "\nResolve duplicates first with 'photree albums fix --new-id'.",
        ]
    )
