"""``photree collection show`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...common.fs import display_path
from ...fsprotocol import PHOTREE_DIR
from ..id import format_collection_external_id
from ..store.metadata import load_collection_metadata
from ..store.protocol import COLLECTION_YAML
from . import collection_app


@collection_app.command("show")
def show_cmd(
    collection_dir: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Collection directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
) -> None:
    """Display collection metadata."""
    cwd = Path.cwd()
    metadata = load_collection_metadata(collection_dir)
    if metadata is None:
        typer.echo(
            f"No collection metadata found: {display_path(collection_dir / PHOTREE_DIR / COLLECTION_YAML, cwd)}\n"
            "Run 'photree collection init' to initialize.",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Collection: {display_path(collection_dir, cwd)}")
    typer.echo(f"  id: {format_collection_external_id(metadata.id)}")
    typer.echo(f"  kind: {metadata.kind}")
    typer.echo(f"  lifecycle: {metadata.lifecycle}")
    typer.echo(f"  albums: {len(metadata.albums)}")
    typer.echo(f"  collections: {len(metadata.collections)}")
    typer.echo(f"  images: {len(metadata.images)}")
    typer.echo(f"  videos: {len(metadata.videos)}")
