"""The ``photree gallery list-media`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.albums.batchcli.listmedia import run_batch_list_media
from photree.albums.batchcli.resolution import resolve_check_batch_albums
from photree.clihelpers.options import (
    OUTPUT_FILE_OPTION,
    OUTPUT_FORMAT_OPTION,
    OutputFormat,
)
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.gallery.cli.app import app


@app.command("list-media")
def list_media_cmd(
    ctx: typer.Context,
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
            help=(
                "Gallery root directory (or resolved from cwd "
                "via .photree/gallery.yaml)."
            ),
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    output_format: OUTPUT_FORMAT_OPTION = OutputFormat.TEXT,
    output_file: OUTPUT_FILE_OPTION = None,
) -> None:
    """List all media items across all albums in the gallery."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    resolved = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    albums, display_base = resolve_check_batch_albums(resolved, None, cwd=cwd)
    run_batch_list_media(
        albums,
        display_base,
        output_format=output_format,
        output_file=output_file,
        cwd=cwd,
    )
