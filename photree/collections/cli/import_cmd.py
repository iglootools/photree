"""``photree collections import`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ...clihelpers.progress import BatchProgressBar
from ...common.exif import try_start_exiftool
from ...common.fs import display_path
from ...collection.importer.import_members import import_collection_members
from ...collection.importer.selection import has_selection
from ...collection.store.collection_discovery import discover_collections
from ...gallery.cli.ops import resolve_gallery_or_exit
from . import collections_app


@collections_app.command("import")
def import_cmd(
    collections_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Parent directory to scan for collections with selections.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    collection_dirs: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--collection-dir",
            "-c",
            help="Collection directory to import (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
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
    """Batch import members for multiple collections."""
    if collections_dir is not None and collection_dirs is not None:
        typer.echo("--dir and --collection-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    cwd = Path.cwd()
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)

    # Resolve collection list
    if collection_dirs is not None:
        candidates = collection_dirs
    else:
        scan_dir = collections_dir if collections_dir is not None else resolved_gallery
        candidates = discover_collections(scan_dir)

    # Filter to collections with selections
    to_import = [d for d in candidates if has_selection(d)]
    skipped = [d for d in candidates if not has_selection(d)]

    if not to_import and not skipped:
        typer.echo("No collections found.")
        raise typer.Exit(code=0)

    with BatchProgressBar(
        total=len(to_import) + len(skipped),
        description="Importing",
        done_description="import",
    ) as progress:
        for col_dir in skipped:
            progress.on_skipped(str(display_path(col_dir, cwd)), "no selection")

        imported = 0
        failed = 0

        exiftool = try_start_exiftool()
        try:
            for col_dir in to_import:
                name = str(display_path(col_dir, cwd))
                progress.on_start(name)
                try:
                    result = import_collection_members(
                        col_dir, resolved_gallery, dry_run=dry_run, exiftool=exiftool
                    )
                except (FileNotFoundError, ValueError) as exc:
                    progress.on_end(name, success=False, error_labels=(str(exc),))
                    failed += 1
                else:
                    if result.success:
                        progress.on_end(name, success=True)
                        imported += 1
                        for warning in result.warnings:
                            typer.echo(
                                f"      warning: [{warning.entry}] {warning.message}"
                            )
                    else:
                        failed += 1
                        progress.on_end(
                            name,
                            success=False,
                            error_labels=tuple(e.message for e in result.errors),
                        )
        finally:
            if exiftool is not None:
                exiftool.__exit__(None, None, None)

    typer.echo(
        f"\n{imported} collection(s) imported, {len(skipped)} skipped, {failed} failed."
    )
    if failed:
        raise typer.Exit(code=1)
