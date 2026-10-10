"""``photree album init`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import err_console
from ...common.formatting import indent
from ...common.fs import display_path
from ..id import format_album_external_id, generate_album_id
from ..store.metadata import (
    album_metadata_path,
    load_album_metadata,
    save_album_metadata,
)
from ..store.protocol import AlbumMetadata
from . import album_app


@album_app.command("init")
def init_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """Initialize album metadata (.photree/album.yaml) with a new album ID."""
    cwd = Path.cwd()
    album_yaml = album_metadata_path(album_dir)
    # A corrupt album.yaml raises InvalidMetadataError (reported by the CLI
    # entry point) rather than reading as "not initialized": writing a new ID
    # over it would orphan every collection reference to the album.
    metadata = load_album_metadata(album_dir)
    if metadata is not None:
        err_console.print(
            f"Album already initialized: {format_album_external_id(metadata.id)}"
        )
        err_console.print(indent(str(display_path(album_yaml, cwd))), markup=False)
        raise typer.Exit(code=1)

    generated_id = generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=generated_id))
    typer.echo(
        f"Created {display_path(album_yaml, cwd)}\n"
        f"Album ID: {format_album_external_id(generated_id)}"
    )
