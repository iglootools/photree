"""``photree albums list`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import AlbumDirOption, DirOption, albums_app
from .batch_ops import resolve_check_batch_albums, run_batch_list_albums


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
    """List all discovered albums with their metadata and media sources."""
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_list_albums(
        albums,
        display_base,
        metadata=metadata,
        output_format=output_format,
        output_file=output_file,
    )
