"""Build the gallery's album index for gallery commands, exiting on missing IDs."""

from pathlib import Path

import typer

from photree.albums.index import AlbumIndex, MissingAlbumIdError
from photree.albums.output import format_missing_ids_report
from photree.clihelpers.console import err_console
from photree.clihelpers.progress import run_with_spinner
from photree.gallery.index import build_album_id_to_path_index


def build_index_or_exit(gallery_dir: Path, cwd: Path) -> AlbumIndex:
    """Build the gallery album index, or exit on missing IDs."""
    try:
        return run_with_spinner(
            "Building album index...",
            lambda: build_album_id_to_path_index(gallery_dir),
        )
    except MissingAlbumIdError as exc:
        err_console.print(
            format_missing_ids_report(exc.albums, "photree gallery fix --id", cwd),
            markup=False,
        )
        raise typer.Exit(code=1) from exc
