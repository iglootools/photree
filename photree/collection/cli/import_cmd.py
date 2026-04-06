"""``photree collection import`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ...clihelpers.console import err_console
from ...common.fs import display_path
from ...fsprotocol import PHOTREE_DIR
from ...gallery.cli.ops import resolve_gallery_or_exit
from ..id import format_collection_external_id
from ..importer.resolve import resolve_entries
from ..importer.selection import SELECTION_CSV, SELECTION_DIR, read_selection
from ..store.metadata import load_collection_metadata, save_collection_metadata
from ..store.protocol import COLLECTION_YAML, CollectionMetadata
from . import collection_app


@collection_app.command("import")
def import_cmd(
    collection_dir: Annotated[
        Path,
        typer.Option(
            "--collection-dir",
            "-c",
            help="Collection directory (must be initialized).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show what would be imported without modifying files.",
        ),
    ] = False,
) -> None:
    """Import members into a collection from to-import/ or to-import.csv."""
    cwd = Path.cwd()
    collection_yaml_path = collection_dir / PHOTREE_DIR / COLLECTION_YAML

    # Load existing collection metadata
    metadata = load_collection_metadata(collection_dir)
    if metadata is None:
        err_console.print(
            f"No collection metadata found: {display_path(collection_yaml_path, cwd)}\n"
            "Run 'photree collection init' to initialize."
        )
        raise typer.Exit(code=1)

    # Read selection
    sources = read_selection(collection_dir)
    if not sources.merged:
        err_console.print(
            f"No selection entries found in {SELECTION_DIR}/ or {SELECTION_CSV}."
        )
        raise typer.Exit(code=1)

    # Resolve gallery
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)

    # Resolve entries
    result = resolve_entries(sources.merged, resolved_gallery)

    if not result.success:
        err_console.print("Resolution errors:")
        for error in result.errors:
            err_console.print(f"  - [{error.entry}] {error.message}")
        raise typer.Exit(code=1)

    # Report what will be imported
    members = result.members
    typer.echo(f"Importing into: {display_path(collection_dir, cwd)}")
    typer.echo(f"  Collection: {format_collection_external_id(metadata.id)}")
    if members.albums:
        typer.echo(f"  albums: {len(members.albums)}")
    if members.collections:
        typer.echo(f"  collections: {len(members.collections)}")
    if members.images:
        typer.echo(f"  images: {len(members.images)}")
    if members.videos:
        typer.echo(f"  videos: {len(members.videos)}")

    if dry_run:
        typer.echo("\nDry run — no changes made.")
        return

    # Merge new members with existing (avoid duplicates)
    updated = CollectionMetadata(
        id=metadata.id,
        kind=metadata.kind,
        lifecycle=metadata.lifecycle,
        albums=_merge_ids(metadata.albums, members.albums),
        collections=_merge_ids(metadata.collections, members.collections),
        images=_merge_ids(metadata.images, members.images),
        videos=_merge_ids(metadata.videos, members.videos),
    )
    save_collection_metadata(collection_dir, updated)

    # Cleanup selection sources
    selection_dir = collection_dir / SELECTION_DIR
    if selection_dir.is_dir():
        for f in selection_dir.iterdir():
            if f.is_file():
                f.unlink()
        # Remove empty dir
        if not any(selection_dir.iterdir()):
            selection_dir.rmdir()

    csv_path = collection_dir / SELECTION_CSV
    if csv_path.is_file():
        csv_path.unlink()

    typer.echo("Import complete.")


def _merge_ids(existing: list[str], new: tuple[str, ...]) -> list[str]:
    """Merge new IDs into existing list, preserving order and avoiding duplicates."""
    seen = set(existing)
    result = list(existing)
    for item in new:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
