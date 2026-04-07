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
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
    validate_collection_config,
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
    members: Annotated[
        Optional[CollectionMembers],
        typer.Option(
            "--members",
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
    strategy: Annotated[
        Optional[CollectionStrategy],
        typer.Option(
            "--strategy",
            help="Rule for member selection: import, date-range, album-series, or chapter.",
        ),
    ] = None,
) -> None:
    """Update collection metadata fields."""
    if members is None and lifecycle is None and strategy is None:
        err_console.print(
            "No fields specified. Use --members, --lifecycle, and/or --strategy to set a value."
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

    new_members = members if members is not None else current.members
    new_lifecycle = lifecycle if lifecycle is not None else current.lifecycle
    new_strategy = strategy if strategy is not None else current.strategy

    validation_error = validate_collection_config(
        new_members, new_lifecycle, new_strategy
    )
    if validation_error is not None:
        err_console.print(validation_error)
        raise typer.Exit(code=1)

    updated = CollectionMetadata(
        id=current.id,
        members=new_members,
        lifecycle=new_lifecycle,
        strategy=new_strategy,
        albums=current.albums,
        collections=current.collections,
        images=current.images,
        videos=current.videos,
    )

    if updated == current:
        typer.echo("No changes — metadata is already up to date.")
        raise typer.Exit(code=0)

    save_collection_metadata(collection_dir, updated)
    changes = [
        *(
            [f"  members: {current.members.value} -> {updated.members.value}"]
            if members is not None and members != current.members
            else []
        ),
        *(
            [f"  lifecycle: {current.lifecycle.value} -> {updated.lifecycle.value}"]
            if lifecycle is not None and lifecycle != current.lifecycle
            else []
        ),
        *(
            [f"  strategy: {current.strategy.value} -> {updated.strategy.value}"]
            if strategy is not None and strategy != current.strategy
            else []
        ),
    ]
    typer.echo(f"Updated {display_path(collection_yaml_path, cwd)}")
    for change in changes:
        typer.echo(change)
