"""The ``photree album init`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.cli.app import app
from photree.album.id import format_album_external_id, generate_album_id
from photree.album.store.metadata import (
    album_metadata_path,
    load_album_metadata,
    save_album_metadata,
)
from photree.album.store.protocol import AlbumMetadata
from photree.clihelpers.console import err_console
from photree.clihelpers.runtime import runtime_of
from photree.common.formatting import indent
from photree.common.fs import display_path


@app.command("init")
def init_cmd(
    ctx: typer.Context,
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
    ] = Path(),
) -> None:
    """Initialize album metadata (.photree/album.yaml) with a new album ID."""
    cwd = runtime_of(ctx).cwd()
    album_yaml = album_metadata_path(album_dir)
    # A corrupt album.yaml raises InvalidMetadataError (reported by the CLI
    # entry point) rather than reading as "not initialized": writing a new ID
    # over it would orphan every collection reference to the album.
    metadata = load_album_metadata(album_dir)
    if metadata is not None:
        err_console.print(
            f"Album already initialized: {format_album_external_id(metadata.id)}",
        )
        err_console.print(indent(str(display_path(album_yaml, cwd))), markup=False)
        raise typer.Exit(code=1)

    generated_id = generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=generated_id))
    typer.echo(
        f"Created {display_path(album_yaml, cwd)}\n"
        f"Album ID: {format_album_external_id(generated_id)}",
    )
