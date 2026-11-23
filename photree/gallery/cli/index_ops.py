"""Build the gallery's album index for gallery commands, exiting on missing IDs."""

from pathlib import Path

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from photree.albums.output import format_missing_ids_report
from photree.clihelpers.console import err_console
from photree.gallery import (
    AlbumIndex,
    MissingAlbumIdError,
    build_album_id_to_path_index,
)


def build_index_or_exit(gallery_dir: Path, cwd: Path) -> AlbumIndex:
    """Build the gallery album index, or exit on missing IDs."""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Building album index...", total=None)
            return build_album_id_to_path_index(gallery_dir)
    except MissingAlbumIdError as exc:
        err_console.print(
            format_missing_ids_report(exc.albums, "photree gallery fix --id", cwd),
            markup=False,
        )
        raise typer.Exit(code=1) from exc
