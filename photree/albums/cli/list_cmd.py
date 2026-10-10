"""``photree albums list`` command."""

from __future__ import annotations

from typing import Annotated

import typer

from ...clihelpers.options import OUTPUT_FILE_OPTION, OUTPUT_FORMAT_OPTION, OutputFormat
from ..batchcli.listing import run_batch_list_albums
from ..batchcli.resolution import resolve_check_batch_albums
from . import AlbumDirOption, DirOption, albums_app


@albums_app.command("list")
def list_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
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
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_list_albums(
        albums,
        display_base,
        metadata=metadata,
        output_format=output_format,
        output_file=output_file,
    )
