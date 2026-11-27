"""The ``photree collection metadata set`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.clihelpers.console import err_console
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import no_fields_error, usage_error
from photree.collection.cli.metadata.app import app
from photree.collection.cli.options import COLLECTION_DIR_OPTION
from photree.collection.output import format_invalid_collection_config
from photree.collection.store.metadata import (
    load_collection_metadata,
    save_collection_metadata,
)
from photree.collection.store.protocol import (
    COLLECTION_YAML,
    CollectionLifecycle,
    CollectionMembers,
    CollectionMetadata,
    CollectionStrategy,
    is_valid_collection_config,
)
from photree.common.formatting import indent
from photree.common.fs import display_path
from photree.foundation.layout import PHOTREE_DIR


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
    """
    Return *current* with every given setting applied, or exit if invalid.

    An invalid combination is a usage error (exit 2), as in
    ``collection init``: the options asked for it.
    """
    updated = current.model_copy(
        update={
            k: v
            for k, v in {
                "members": members,
                "lifecycle": lifecycle,
                "strategy": strategy,
            }.items()
            if v is not None
        },
    )
    config = (updated.members, updated.lifecycle, updated.strategy)
    if not is_valid_collection_config(*config):
        raise usage_error(format_invalid_collection_config(*config), markup=False)
    return updated


def _media_dropped_by(
    current: CollectionMetadata,
    updated: CollectionMetadata,
) -> tuple[int, int]:
    """
    Return how many images and videos the switch to smart will lose.

    A smart collection holds only albums and collections, and the next
    'gallery refresh' empties its image and video lists.
    """
    switching = (
        current.members != CollectionMembers.SMART
        and updated.members == CollectionMembers.SMART
    )
    return (len(updated.images), len(updated.videos)) if switching else (0, 0)


def _require_force_to_drop_media(
    dropped: tuple[int, int],
    collection_dir: Path,
    cwd: Path,
    *,
    force: bool,
) -> None:
    """Exit unless nothing is dropped or *force* is given; warn when it is."""
    images, videos = dropped
    if images == 0 and videos == 0:
        return
    problem = (
        f"{display_path(collection_dir, cwd)} has {images} image(s) and "
        f"{videos} video(s): a smart collection holds only albums and "
        "collections, so the next 'photree gallery refresh' drops them."
    )
    if force:
        err_console.print(f"warning: {problem}", markup=False)
    else:
        err_console.print(
            f"{problem}\nRe-run with --force to switch to smart anyway.",
            markup=False,
        )
        raise typer.Exit(code=1)


def _format_changes(
    current: CollectionMetadata,
    updated: CollectionMetadata,
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


@app.command("set")
def set_cmd(
    ctx: typer.Context,
    collection_dir: COLLECTION_DIR_OPTION = Path(),
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
            help=(
                "How the collection is managed: explicit (user) "
                "or implicit (from album series)."
            ),
        ),
    ] = None,
    strategy: Annotated[
        CollectionStrategy | None,
        typer.Option(
            "--strategy",
            help=(
                "Rule for member selection: import, "
                "date-range, album-series, or chapter."
            ),
        ),
    ] = None,
    *,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help=(
                "Switch a collection holding images or videos to smart members, "
                "which the next 'gallery refresh' drops."
            ),
        ),
    ] = False,
) -> None:
    """Update collection metadata fields."""
    if members is None and lifecycle is None and strategy is None:
        raise no_fields_error(("--members", "--lifecycle", "--strategy"))

    cwd = runtime_of(ctx).cwd()
    current = _load_or_exit(collection_dir, cwd)
    updated = _apply_settings(current, members, lifecycle, strategy)
    if updated == current:
        typer.echo("No changes — metadata is already up to date.")
        raise typer.Exit(code=0)
    _require_force_to_drop_media(
        _media_dropped_by(current, updated),
        collection_dir,
        cwd,
        force=force,
    )

    save_collection_metadata(collection_dir, updated)
    yaml_path = display_path(collection_dir / PHOTREE_DIR / COLLECTION_YAML, cwd)
    typer.echo(f"Updated {yaml_path}")
    typer.echo(indent("\n".join(_format_changes(current, updated))))
