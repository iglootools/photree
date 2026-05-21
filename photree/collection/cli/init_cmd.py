"""``photree collection init`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...common.fs import display_path
from ...fsprotocol import PHOTREE_DIR
from ..id import format_collection_external_id, generate_collection_id
from ..store.metadata import load_collection_metadata, save_collection_metadata
from ..store.protocol import (
    COLLECTION_YAML,
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
    validate_collection_config,
)
from . import collection_app


@collection_app.command("init")
def init_cmd(
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
        CollectionMembers,
        typer.Option(
            "--members",
            help="How members are determined: smart (auto by date range) or manual.",
        ),
    ] = CollectionMembers.MANUAL,
    lifecycle: Annotated[
        CollectionLifecycle,
        typer.Option(
            "--lifecycle",
            help="How the collection is managed: explicit (user) or implicit (from album series).",
        ),
    ] = CollectionLifecycle.EXPLICIT,
    strategy: Annotated[
        CollectionStrategy,
        typer.Option(
            "--strategy",
            help="Rule for member selection: import, date-range, album-series, or chapter.",
        ),
    ] = CollectionStrategy.IMPORT,
) -> None:
    """Initialize collection metadata (.photree/collection.yaml)."""
    cwd = Path.cwd()
    metadata = load_collection_metadata(collection_dir)
    if metadata is not None:
        typer.echo(
            f"Collection already initialized: {format_collection_external_id(metadata.id)}\n"
            f"  {display_path(collection_dir / PHOTREE_DIR / COLLECTION_YAML, cwd)}\n"
            "Use 'photree collection metadata set' to change settings.",
            err=True,
        )
        raise typer.Exit(code=1)

    validation_error = validate_collection_config(members, lifecycle, strategy)
    if validation_error is not None:
        typer.echo(validation_error, err=True)
        raise typer.Exit(code=1)

    generated_id = generate_collection_id()
    save_collection_metadata(
        collection_dir,
        CollectionMetadata(
            id=generated_id,
            members=members,
            lifecycle=lifecycle,
            strategy=strategy,
        ),
    )
    collection_yaml = collection_dir / PHOTREE_DIR / COLLECTION_YAML
    typer.echo(
        f"Created {display_path(collection_yaml, cwd)}\n"
        f"Collection ID: {format_collection_external_id(generated_id)}\n"
        f"  members: {members}\n"
        f"  lifecycle: {lifecycle}\n"
        f"  strategy: {strategy}"
    )
