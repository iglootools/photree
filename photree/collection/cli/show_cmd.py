"""``photree collection show`` command."""

from __future__ import annotations

from pathlib import Path

import typer

from ...clihelpers.console import err_console
from ...common.formatting import indent
from ...common.fs import display_path
from ...foundation.layout import PHOTREE_DIR
from ..id import format_collection_external_id
from ..naming import ParsedCollectionName, parse_collection_name
from ..store.metadata import load_collection_metadata
from ..store.protocol import COLLECTION_YAML, CollectionMetadata
from . import collection_app
from .options import COLLECTION_DIR_OPTION


def format_collection_details(
    dir_name: str, metadata: CollectionMetadata, parsed: ParsedCollectionName
) -> list[str]:
    """``key: value`` detail lines (unindented) for one collection."""
    return [
        f"directory: {dir_name}",
        f"id: {format_collection_external_id(metadata.id)}",
        f"members: {metadata.members}",
        f"lifecycle: {metadata.lifecycle}",
        f"strategy: {metadata.strategy}",
        *([f"date: {parsed.date}"] if parsed.date is not None else []),
        f"title: {parsed.title}",
        *([f"location: {parsed.location}"] if parsed.location is not None else []),
        *(["private: yes"] if parsed.private else []),
        f"albums: {len(metadata.albums)}",
        f"collections: {len(metadata.collections)}",
        f"images: {len(metadata.images)}",
        f"videos: {len(metadata.videos)}",
    ]


@collection_app.command("show")
def show_cmd(collection_dir: COLLECTION_DIR_OPTION = Path(".")) -> None:
    """Display collection metadata and parsed name."""
    cwd = Path.cwd()
    metadata = load_collection_metadata(collection_dir)
    if metadata is None:
        yaml_path = display_path(collection_dir / PHOTREE_DIR / COLLECTION_YAML, cwd)
        err_console.print(
            f"No collection metadata found: {yaml_path}\n"
            "Run 'photree collection init --collection-dir "
            f'"{display_path(collection_dir, cwd)}"\' to initialize.',
            markup=False,
        )
        raise typer.Exit(code=1)

    details = format_collection_details(
        collection_dir.name, metadata, parse_collection_name(collection_dir.name)
    )
    typer.echo(f"Collection: {display_path(collection_dir, cwd)}")
    typer.echo(indent("\n".join(details)))
