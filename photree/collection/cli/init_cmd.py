"""``photree collection init`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import err_console
from ...common.formatting import indent
from ...common.fs import display_path
from ...fsprotocol import PHOTREE_DIR
from ..id import format_collection_external_id
from ..init import CollectionAlreadyInitializedError, init_collection
from ..store.protocol import (
    COLLECTION_YAML,
    CollectionLifecycle,
    CollectionMembers,
    CollectionStrategy,
    validate_collection_config,
)
from . import collection_app
from .options import COLLECTION_DIR_OPTION


@collection_app.command("init")
def init_cmd(
    collection_dir: COLLECTION_DIR_OPTION = Path("."),
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
    collection_yaml = display_path(collection_dir / PHOTREE_DIR / COLLECTION_YAML, cwd)

    validation_error = validate_collection_config(members, lifecycle, strategy)
    if validation_error is not None:
        err_console.print(validation_error, markup=False)
        raise typer.Exit(code=1)

    try:
        metadata = init_collection(
            collection_dir, members=members, lifecycle=lifecycle, strategy=strategy
        )
    except CollectionAlreadyInitializedError as exc:
        err_console.print(
            "Collection already initialized: "
            f"{format_collection_external_id(exc.existing_id)}\n"
            f"{indent(str(collection_yaml))}\n"
            "Run 'photree collection metadata set --collection-dir "
            f'"{display_path(collection_dir, cwd)}"\' to change settings.',
            markup=False,
        )
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created {collection_yaml}")
    typer.echo(f"Collection ID: {format_collection_external_id(metadata.id)}")
    typer.echo(
        indent(f"members: {members}\nlifecycle: {lifecycle}\nstrategy: {strategy}")
    )
