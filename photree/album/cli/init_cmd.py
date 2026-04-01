"""``photree album init`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import album_app
from ...fs import (
    ALBUM_YAML,
    AlbumMetadata,
    PHOTREE_DIR,
    display_path,
    format_album_external_id,
    generate_album_id,
    load_album_metadata,
    save_album_metadata,
)


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
    metadata = load_album_metadata(album_dir)
    if metadata is not None:
        typer.echo(
            f"Album already initialized: {format_album_external_id(metadata.id)}\n"
            f"  {display_path(album_dir / PHOTREE_DIR / ALBUM_YAML, cwd)}",
            err=True,
        )
        raise typer.Exit(code=1)

    generated_id = generate_album_id()
    save_album_metadata(album_dir, AlbumMetadata(id=generated_id))
    album_yaml = album_dir / PHOTREE_DIR / ALBUM_YAML
    typer.echo(
        f"Created {display_path(album_yaml, cwd)}\n"
        f"Album ID: {format_album_external_id(generated_id)}"
    )
