"""The ``photree collection init`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.clihelpers.console import err_console
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import usage_error
from photree.collection.cli.app import app
from photree.collection.cli.options import COLLECTION_DIR_OPTION
from photree.collection.id import format_collection_external_id
from photree.collection.init import CollectionAlreadyInitializedError, init_collection
from photree.collection.store.protocol import (
    COLLECTION_YAML,
    CollectionLifecycle,
    CollectionMembers,
    CollectionStrategy,
    validate_collection_config,
)
from photree.common.formatting import indent
from photree.common.fs import display_path
from photree.foundation.layout import PHOTREE_DIR


@app.command("init")
def init_cmd(
    ctx: typer.Context,
    collection_dir: COLLECTION_DIR_OPTION = Path(),
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
            help=(
                "How the collection is managed: explicit (user) "
                "or implicit (from album series)."
            ),
        ),
    ] = CollectionLifecycle.EXPLICIT,
    strategy: Annotated[
        CollectionStrategy,
        typer.Option(
            "--strategy",
            help=(
                "Rule for member selection: import, "
                "date-range, album-series, or chapter."
            ),
        ),
    ] = CollectionStrategy.IMPORT,
) -> None:
    """Initialize collection metadata (.photree/collection.yaml)."""
    cwd = runtime_of(ctx).cwd()
    collection_yaml = display_path(collection_dir / PHOTREE_DIR / COLLECTION_YAML, cwd)

    validation_error = validate_collection_config(members, lifecycle, strategy)
    if validation_error is not None:
        raise usage_error(validation_error, markup=False)

    try:
        metadata = init_collection(
            collection_dir,
            members=members,
            lifecycle=lifecycle,
            strategy=strategy,
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
        indent(f"members: {members}\nlifecycle: {lifecycle}\nstrategy: {strategy}"),
    )
