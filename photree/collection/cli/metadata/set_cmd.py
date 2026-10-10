"""``photree collection metadata set`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ....clihelpers.console import err_console
from ....common.formatting import indent
from ....common.fs import display_path
from ....foundation.layout import PHOTREE_DIR
from ...store.metadata import load_collection_metadata, save_collection_metadata
from ...store.protocol import (
    COLLECTION_YAML,
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
    validate_collection_config,
)
from ..options import COLLECTION_DIR_OPTION
from . import collection_metadata_app


def _load_or_exit(collection_dir: Path, cwd: Path) -> CollectionMetadata:
    current = load_collection_metadata(collection_dir)
    if current is None:
        yaml_path = display_path(collection_dir / PHOTREE_DIR / COLLECTION_YAML, cwd)
        err_console.print(
            f"No collection metadata found: {yaml_path}\n"
            "Run 'photree collection init --collection-dir "
            f'"{display_path(collection_dir, cwd)}"\' to initialize.',
            markup=False,
        )
        raise typer.Exit(code=1)
    return current


def _apply_settings(
    current: CollectionMetadata,
    members: CollectionMembers | None,
    lifecycle: CollectionLifecycle | None,
    strategy: CollectionStrategy | None,
) -> CollectionMetadata:
    """Return *current* with every given setting applied, or exit if invalid."""
    updated = current.model_copy(
        update={
            k: v
            for k, v in {
                "members": members,
                "lifecycle": lifecycle,
                "strategy": strategy,
            }.items()
            if v is not None
        }
    )
    validation_error = validate_collection_config(
        updated.members, updated.lifecycle, updated.strategy
    )
    if validation_error is not None:
        err_console.print(validation_error, markup=False)
        raise typer.Exit(code=1)
    return updated


def _format_changes(
    current: CollectionMetadata, updated: CollectionMetadata
) -> list[str]:
    """``field: old -> new`` lines (unindented) for each changed setting."""
    return [
        f"{field}: {old.value} -> {new.value}"
        for field, old, new in (
            ("members", current.members, updated.members),
            ("lifecycle", current.lifecycle, updated.lifecycle),
            ("strategy", current.strategy, updated.strategy),
        )
        if old != new
    ]


@collection_metadata_app.command("set")
def set_cmd(
    collection_dir: COLLECTION_DIR_OPTION = Path("."),
    members: Annotated[
        CollectionMembers | None,
        typer.Option(
            "--members",
            help="How members are determined: smart (auto by date range) or manual.",
        ),
    ] = None,
    lifecycle: Annotated[
        CollectionLifecycle | None,
        typer.Option(
            "--lifecycle",
            help="How the collection is managed: explicit (user) or implicit (from album series).",
        ),
    ] = None,
    strategy: Annotated[
        CollectionStrategy | None,
        typer.Option(
            "--strategy",
            help="Rule for member selection: import, date-range, album-series, or chapter.",
        ),
    ] = None,
) -> None:
    """Update collection metadata fields."""
    if members is None and lifecycle is None and strategy is None:
        err_console.print(
            "No fields specified. Use --members, --lifecycle, and/or --strategy "
            "to set a value."
        )
        raise typer.Exit(code=1)

    cwd = Path.cwd()
    current = _load_or_exit(collection_dir, cwd)
    updated = _apply_settings(current, members, lifecycle, strategy)
    if updated == current:
        typer.echo("No changes — metadata is already up to date.")
        raise typer.Exit(code=0)

    save_collection_metadata(collection_dir, updated)
    yaml_path = display_path(collection_dir / PHOTREE_DIR / COLLECTION_YAML, cwd)
    typer.echo(f"Updated {yaml_path}")
    typer.echo(indent("\n".join(_format_changes(current, updated))))
