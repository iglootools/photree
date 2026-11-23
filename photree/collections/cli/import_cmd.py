"""The ``photree collections import`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.clihelpers.console import console, err_console
from photree.clihelpers.options import DRY_RUN_OPTION, GALLERY_DIR_OPTION
from photree.clihelpers.progress import BatchProgressBar
from photree.clihelpers.resolution import (
    format_invalid_metadata,
    resolve_gallery_or_exit,
)
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.sysdeps import EXIF_DEPS, require_system_deps
from photree.clihelpers.usage import mutually_exclusive_error
from photree.collection.importer.import_members import (
    CollectionImportError,
    CollectionImportResult,
)
from photree.collection.importer.output import (
    format_import_error,
    format_resolution_warning,
    format_result_errors,
    format_unreadable_warnings,
)
from photree.collection.store.collection_discovery import discover_collections
from photree.collections.cli.app import app
from photree.collections.cmd_handler.import_members import (
    BatchImportResult,
    CollectionImportOutcome,
    batch_import,
)
from photree.common.exif import exiftool_session
from photree.common.formatting import format_dry_run, indent
from photree.common.fs import display_path
from photree.common.sysdeps import WhichFn
from photree.foundation.layout import COLLECTIONS_DIR
from photree.foundation.metadata_io import InvalidMetadataError


def _resolve_candidates(
    collections_dir: Path | None,
    collection_dirs: list[Path] | None,
    gallery_dir: Path,
) -> list[Path]:
    match (collection_dirs, collections_dir):
        case (list(), _):
            return collection_dirs
        case (None, Path()):
            return discover_collections(collections_dir)
        case _:
            return discover_collections(gallery_dir / COLLECTIONS_DIR)


def _format_os_error(exc: OSError, cwd: Path) -> str:
    reason = exc.strerror or type(exc).__name__
    return (
        f"{reason}: {display_path(Path(exc.filename), cwd)}"
        if exc.filename is not None
        else reason
    )


def _format_errors(outcome: CollectionImportOutcome, cwd: Path) -> list[str]:
    """Every reason *outcome* failed, one unindented line each."""
    match (outcome.result, outcome.error):
        case (CollectionImportResult() as result, _):
            return format_result_errors(result, cwd)
        case (_, CollectionImportError() as exc):
            return [format_import_error(exc, cwd)]
        case (_, InvalidMetadataError() as exc):
            return [format_invalid_metadata(exc, cwd)]
        case (_, OSError() as exc):
            return [_format_os_error(exc, cwd)]
        case _:
            return []


def _print_unreadable(outcomes: tuple[CollectionImportOutcome, ...], cwd: Path) -> None:
    """Print, once, each album or collection the shared gallery scan could not read."""
    results = [o.result for o in outcomes if o.result is not None]
    for warning in format_unreadable_warnings(
        dict.fromkeys(d for r in results for d in r.unreadable_albums),
        dict.fromkeys(d for r in results for d in r.unreadable_collections),
        cwd,
    ):
        err_console.print(warning, markup=False)


def _print_warnings(outcomes: tuple[CollectionImportOutcome, ...], cwd: Path) -> None:
    """
    Print each collection's warnings under its path.

    Printed once the progress bar has closed: a line printed while it is
    live lands in the middle of its display.
    """
    warned = [
        (o.collection_dir, o.result.warnings)
        for o in outcomes
        if o.result is not None and o.result.warnings
    ]
    if warned:
        console.print(
            "\n".join(
                [
                    "\nWarnings:",
                    *(
                        indent(
                            f"{display_path(collection_dir, cwd)}\n{indent(lines)}",
                        )
                        for collection_dir, warnings in warned
                        for lines in [
                            "\n".join(format_resolution_warning(w) for w in warnings),
                        ]
                    ),
                ],
            ),
            markup=False,
        )


def _print_summary(result: BatchImportResult, *, dry_run: bool, cwd: Path) -> None:
    failures = result.failures
    imported = len(result.outcomes) - len(failures)
    verb = "would be imported" if dry_run else "imported"
    typer.echo(
        format_dry_run(
            f"\n{imported} collection(s) {verb}, {len(result.skipped)} skipped, "
            f"{len(failures)} failed.",
            dry_run=dry_run,
        ),
    )
    if failures:
        err_console.print("\nFailed collections:")
        err_console.print(
            "\n".join(
                indent(f"{display_path(o.collection_dir, cwd)}\n{indent(reasons)}")
                for o in failures
                for reasons in ["\n".join(_format_errors(o, cwd))]
            ),
            markup=False,
        )
        err_console.print("\nTo investigate failures:")
        err_console.print(
            "\n".join(
                indent(
                    "photree collection import --collection-dir "
                    f'"{display_path(o.collection_dir, cwd)}" --dry-run',
                )
                for o in failures
            ),
            markup=False,
        )
        raise typer.Exit(code=1)


@app.command("import")
def import_cmd(
    ctx: typer.Context,
    collections_dir: Annotated[
        Path | None,
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
        list[Path] | None,
        typer.Option(
            "--collection-dir",
            "-c",
            help="Collection directory to import (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    gallery_dir: GALLERY_DIR_OPTION = None,
    *,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Batch import members for multiple collections."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    which = runtime.which
    if collections_dir is not None and collection_dirs is not None:
        raise mutually_exclusive_error(
            ("--dir", "--collection-dir"),
            command="collections import",
        )

    # Selection entries are resolved to media items by EXIF timestamp.
    require_system_deps(EXIF_DEPS, which=which)

    resolved_gallery = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    candidates = _resolve_candidates(collections_dir, collection_dirs, resolved_gallery)
    if not candidates:
        typer.echo("No collections found.")
        raise typer.Exit(code=0)

    result = _import_all(
        candidates,
        resolved_gallery,
        dry_run=dry_run,
        cwd=cwd,
        which=which,
    )
    _print_unreadable(result.outcomes, cwd)
    _print_warnings(result.outcomes, cwd)
    _print_summary(result, dry_run=dry_run, cwd=cwd)


def _import_all(
    candidates: list[Path],
    gallery_dir: Path,
    *,
    dry_run: bool,
    cwd: Path,
    which: WhichFn,
) -> BatchImportResult:
    """Import every candidate that has a selection, behind a progress bar."""
    with (
        exiftool_session(which=which) as exiftool,
        BatchProgressBar(
            total=len(candidates),
            description="Importing",
            done_description="import",
        ) as progress,
    ):
        return batch_import(
            candidates,
            gallery_dir,
            dry_run=dry_run,
            exiftool=exiftool,
            display_fn=lambda p: str(display_path(p, cwd)),
            on_skipped=lambda name: progress.on_skipped(name, "no selection"),
            on_start=progress.on_start,
            on_end=progress.on_end,
        )
