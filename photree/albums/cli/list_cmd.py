"""The ``photree albums list`` command."""

from typing import Annotated

import typer

from photree.albums.batchcli.listing import run_batch_list_albums
from photree.albums.batchcli.resolution import resolve_check_batch_albums
from photree.albums.cli.app import app
from photree.albums.cli.options import ALBUM_DIR_OPTION, DIR_OPTION
from photree.clihelpers.options import (
    OUTPUT_FILE_OPTION,
    OUTPUT_FORMAT_OPTION,
    OutputFormat,
)
from photree.clihelpers.runtime import runtime_of


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    base_dir: DIR_OPTION = None,
    album_dirs: ALBUM_DIR_OPTION = None,
    *,
    metadata: Annotated[
        bool,
        typer.Option(
            "--metadata/--no-metadata",
            help="Show parsed album metadata and media sources (default: enabled).",
        ),
    ] = True,
    output_format: OUTPUT_FORMAT_OPTION = OutputFormat.TEXT,
    output_file: OUTPUT_FILE_OPTION = None,
) -> None:
    """List all discovered albums with their metadata and media sources."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs, cwd=cwd)
    run_batch_list_albums(
        albums,
        display_base,
        metadata=metadata,
        output_format=output_format,
        output_file=output_file,
        cwd=cwd,
    )
