"""``photree collection metadata set`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ....clihelpers.console import err_console
from ....common.fs import display_path
from ....fsprotocol import PHOTREE_DIR
from ...store.metadata import load_collection_metadata, save_collection_metadata
from ...store.protocol import (
    COLLECTION_YAML,
    CollectionKind,
    CollectionLifecycle,
    CollectionMetadata,
)
from . import collection_metadata_app


@collection_metadata_app.command("set")
def set_cmd(
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
    kind: Annotated[
        Optional[CollectionKind],
        typer.Option(
            "--kind",
            help="How members are determined: smart (auto by date range) or manual.",
        ),
    ] = None,
    lifecycle: Annotated[
        Optional[CollectionLifecycle],
        typer.Option(
            "--lifecycle",
            help="How the collection is managed: explicit (user) or implicit (from album series).",
        ),
    ] = None,
) -> None:
    """Update collection metadata fields."""
    if kind is None and lifecycle is None:
        err_console.print(
            "No fields specified. Use --kind and/or --lifecycle to set a value."
        )
        raise typer.Exit(code=1)

    cwd = Path.cwd()
    collection_yaml_path = collection_dir / PHOTREE_DIR / COLLECTION_YAML
    current = load_collection_metadata(collection_dir)
    if current is None:
        err_console.print(
            f"No collection metadata found: {display_path(collection_yaml_path, cwd)}\n"
            "Run 'photree collection init' to initialize."
        )
        raise typer.Exit(code=1)

    updated = CollectionMetadata(
        id=current.id,
        kind=kind if kind is not None else current.kind,
        lifecycle=lifecycle if lifecycle is not None else current.lifecycle,
        albums=current.albums,
        collections=current.collections,
        images=current.images,
        videos=current.videos,
    )

    if updated == current:
        typer.echo("No changes — metadata is already up to date.")
        raise typer.Exit(code=0)

    save_collection_metadata(collection_dir, updated)
    changes: list[str] = []
    if kind is not None and kind != current.kind:
        changes.append(f"  kind: {current.kind.value} -> {updated.kind.value}")
    if lifecycle is not None and lifecycle != current.lifecycle:
        changes.append(
            f"  lifecycle: {current.lifecycle.value} -> {updated.lifecycle.value}"
        )
    typer.echo(f"Updated {display_path(collection_yaml_path, cwd)}")
    for change in changes:
        typer.echo(change)
