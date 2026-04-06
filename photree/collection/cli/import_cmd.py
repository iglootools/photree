"""``photree collection import`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ...clihelpers.console import err_console
from ...common.exif import try_start_exiftool
from ...common.fs import display_path
from ...gallery.cli.ops import resolve_gallery_or_exit
from ..id import format_collection_external_id
from ..importer.import_members import import_collection_members
from ..store.metadata import load_collection_metadata
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
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)

    metadata = load_collection_metadata(collection_dir)
    if metadata is None:
        err_console.print(
            f"No collection metadata found in {display_path(collection_dir, cwd)}\n"
            "Run 'photree collection init' to initialize."
        )
        raise typer.Exit(code=1)

    exiftool = try_start_exiftool()
    try:
        result = import_collection_members(
            collection_dir, resolved_gallery, dry_run=dry_run, exiftool=exiftool
        )
    except FileNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)

    if not result.success:
        err_console.print("Resolution errors:")
        for error in result.errors:
            err_console.print(f"  - [{error.entry}] {error.message}")
        raise typer.Exit(code=1)

    if result.warnings:
        for warning in result.warnings:
            typer.echo(f"  warning: [{warning.entry}] {warning.message}")

    members = result.members
    typer.echo(f"Imported into: {display_path(collection_dir, cwd)}")
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
    else:
        typer.echo("Import complete.")
