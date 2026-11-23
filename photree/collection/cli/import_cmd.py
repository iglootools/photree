"""The ``photree collection import`` command."""

from pathlib import Path
from typing import Annotated

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from photree.clihelpers.console import console, err_console
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.sysdeps import EXIF_DEPS, require_system_deps
from photree.collection.cli.app import app
from photree.collection.id import format_collection_external_id
from photree.collection.importer.import_members import (
    CollectionImportError,
    CollectionImportResult,
    import_collection_members,
)
from photree.collection.importer.output import (
    format_import_error,
    format_member_counts,
    format_resolution_warning,
    format_result_errors,
    format_unreadable_warnings,
)
from photree.collection.importer.resolve import scan_gallery
from photree.common.exif import ExifTagReader, exiftool_session
from photree.common.formatting import format_dry_run, indent
from photree.common.fs import display_path


def _run_import(
    collection_dir: Path,
    gallery_dir: Path,
    *,
    dry_run: bool,
    exiftool: ExifTagReader | None,
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
                collection_dir,
                lambda: scan_gallery(gallery_dir),
                dry_run=dry_run,
                exiftool=exiftool,
            )
    except CollectionImportError as exc:
        err_console.print(format_import_error(exc, cwd), markup=False)
        raise typer.Exit(code=1) from exc


def _print_result(result: CollectionImportResult, *, dry_run: bool, cwd: Path) -> None:
    for warning in format_unreadable_warnings(
        result.unreadable_albums,
        result.unreadable_collections,
        cwd,
    ):
        err_console.print(warning, markup=False)
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

    into = "Would import into" if dry_run else "Imported into"
    typer.echo(f"{into}: {display_path(result.collection_dir, cwd)}")
    typer.echo(
        indent(
            "\n".join(
                [
                    (
                        "Collection: "
                        f"{format_collection_external_id(result.collection_id)}"
                    ),
                    *format_member_counts(result.members),
                ],
            ),
        ),
    )
    typer.echo(
        format_dry_run("\nNo changes made.", dry_run=True)
        if dry_run
        else "Import complete.",
    )


@app.command("import")
def import_cmd(
    ctx: typer.Context,
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
    ] = Path(),
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
            help=(
                "Gallery root directory (or resolved from cwd "
                "via .photree/gallery.yaml)."
            ),
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    *,
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
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    which = runtime.which
    # Selection entries are resolved to media items by EXIF timestamp.
    require_system_deps(EXIF_DEPS, which=which)

    resolved_gallery = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    with exiftool_session(which=which) as exiftool:
        result = _run_import(
            collection_dir,
            resolved_gallery,
            dry_run=dry_run,
            exiftool=exiftool,
            cwd=cwd,
        )
    _print_result(result, dry_run=dry_run, cwd=cwd)
