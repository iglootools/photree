"""``photree collection import`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from exiftool import ExifToolHelper  # type: ignore[import-untyped]
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...clihelpers.console import console, err_console
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...clihelpers.sysdeps import EXIF_DEPS, require_system_deps
from ...common.exif import exiftool_session
from ...common.formatting import indent
from ...common.fs import display_path
from ..id import format_collection_external_id
from ..importer.import_members import (
    CollectionImportError,
    CollectionImportResult,
    import_collection_members,
)
from ..importer.output import (
    format_import_error,
    format_member_counts,
    format_resolution_warning,
    format_result_errors,
)
from . import collection_app


def _run_import(
    collection_dir: Path,
    gallery_dir: Path,
    *,
    dry_run: bool,
    exiftool: ExifToolHelper | None,
    cwd: Path,
) -> CollectionImportResult:
    """Run the import behind a spinner, exiting on a collection-level error."""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Resolving members...", total=None)
            return import_collection_members(
                collection_dir, gallery_dir, dry_run=dry_run, exiftool=exiftool
            )
    except CollectionImportError as exc:
        err_console.print(format_import_error(exc, cwd), markup=False)
        raise typer.Exit(code=1) from exc


def _print_result(result: CollectionImportResult, *, dry_run: bool, cwd: Path) -> None:
    # markup=False: entries and paths are user text and may contain [brackets]
    # (e.g. a "[private]" tag) that Rich would otherwise swallow as markup.
    if not result.success:
        err_console.print("Resolution errors:")
        err_console.print(
            "\n".join(
                indent(f"- {line}") for line in format_result_errors(result, cwd)
            ),
            markup=False,
        )
        raise typer.Exit(code=1)

    for warning in result.warnings:
        console.print(indent(format_resolution_warning(warning)), markup=False)

    typer.echo(f"Imported into: {display_path(result.collection_dir, cwd)}")
    typer.echo(
        indent(
            "\n".join(
                [
                    f"Collection: {format_collection_external_id(result.collection_id)}",
                    *format_member_counts(result.members),
                ]
            )
        )
    )
    typer.echo("\nDry run — no changes made." if dry_run else "Import complete.")


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
        Path | None,
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
    # Selection entries are resolved to media items by EXIF timestamp.
    require_system_deps(EXIF_DEPS)

    cwd = Path.cwd()
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    with exiftool_session() as exiftool:
        result = _run_import(
            collection_dir,
            resolved_gallery,
            dry_run=dry_run,
            exiftool=exiftool,
            cwd=cwd,
        )
    _print_result(result, dry_run=dry_run, cwd=cwd)
