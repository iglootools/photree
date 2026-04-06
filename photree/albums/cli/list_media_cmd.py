"""``photree albums list-media`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import AlbumDirOption, DirOption, albums_app
from .batch_ops import run_batch_list_media
from .ops import resolve_check_batch_albums


@albums_app.command("list-media")
def list_media_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: text (default) or csv.",
        ),
    ] = "text",
    output_file: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Write output to a file instead of stdout.",
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """List all media items across multiple albums."""
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_list_media(
        albums,
        display_base,
        output_format=output_format,
        output_file=output_file,
    )
