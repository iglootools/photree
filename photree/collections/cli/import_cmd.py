"""``photree collections import`` command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...clihelpers.console import console, err_console
from ...clihelpers.progress import BatchProgressBar
from ...clihelpers.resolution import format_invalid_metadata, resolve_gallery_or_exit
from ...clihelpers.sysdeps import EXIF_DEPS, require_system_deps
from ...collection.importer.import_members import (
    CollectionImportError,
    import_collection_members,
)
from ...collection.importer.output import (
    format_import_error,
    format_resolution_warning,
    format_result_errors,
)
from ...collection.importer.selection import has_selection
from ...collection.store.collection_discovery import discover_collections
from ...common.exif import exiftool_session
from ...common.formatting import indent
from ...common.fs import display_path
from ...foundation.metadata_io import InvalidMetadataError
from . import collections_app


@dataclass(frozen=True)
class _ImportOutcome:
    """One collection's import: failure reasons (empty on success)."""

    collection_dir: Path
    errors: tuple[str, ...]

    @property
    def success(self) -> bool:
        return not self.errors


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
            return discover_collections(gallery_dir)


def _import_one(
    col_dir: Path,
    gallery_dir: Path,
    *,
    dry_run: bool,
    exiftool: ExifToolHelper | None,
    cwd: Path,
) -> _ImportOutcome:
    """Import one collection; every failure becomes the outcome's reasons."""
    try:
        result = import_collection_members(
            col_dir, gallery_dir, dry_run=dry_run, exiftool=exiftool
        )
    except CollectionImportError as exc:
        return _ImportOutcome(col_dir, (format_import_error(exc, cwd),))
    except InvalidMetadataError as exc:
        return _ImportOutcome(col_dir, (format_invalid_metadata(exc, cwd),))
    except OSError as exc:
        return _ImportOutcome(col_dir, (_format_os_error(exc, cwd),))
    for warning in result.warnings:
        console.print(indent(format_resolution_warning(warning), 3), markup=False)
    return _ImportOutcome(col_dir, tuple(format_result_errors(result, cwd)))


def _format_os_error(exc: OSError, cwd: Path) -> str:
    reason = exc.strerror or type(exc).__name__
    return (
        f"{reason}: {display_path(Path(exc.filename), cwd)}"
        if exc.filename is not None
        else reason
    )


def _print_summary(
    outcomes: list[_ImportOutcome], skipped: int, *, dry_run: bool, cwd: Path
) -> None:
    failures = [o for o in outcomes if not o.success]
    imported = len(outcomes) - len(failures)
    verb = "would be imported" if dry_run else "imported"
    typer.echo(
        f"\n{imported} collection(s) {verb}, {skipped} skipped, {len(failures)} failed."
    )
    if failures:
        err_console.print("\nFailed collections:")
        err_console.print(
            "\n".join(
                indent(f"{display_path(o.collection_dir, cwd)}\n{indent(reasons)}")
                for o in failures
                for reasons in ["\n".join(o.errors)]
            ),
            markup=False,
        )
        err_console.print("\nTo investigate failures:")
        err_console.print(
            "\n".join(
                indent(
                    "photree collection import --collection-dir "
                    f'"{display_path(o.collection_dir, cwd)}" --dry-run'
                )
                for o in failures
            ),
            markup=False,
        )
        raise typer.Exit(code=1)


@collections_app.command("import")
def import_cmd(
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
    """Batch import members for multiple collections."""
    if collections_dir is not None and collection_dirs is not None:
        err_console.print(
            "--dir and --collection-dir are mutually exclusive.\n"
            "Run 'photree collections import --help' for usage."
        )
        raise typer.Exit(code=1)

    # Selection entries are resolved to media items by EXIF timestamp.
    require_system_deps(EXIF_DEPS)

    cwd = Path.cwd()
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    candidates = _resolve_candidates(collections_dir, collection_dirs, resolved_gallery)
    if not candidates:
        typer.echo("No collections found.")
        raise typer.Exit(code=0)

    outcomes, skipped = _import_all(candidates, resolved_gallery, dry_run, cwd)
    _print_summary(outcomes, skipped, dry_run=dry_run, cwd=cwd)


def _import_all(
    candidates: list[Path], gallery_dir: Path, dry_run: bool, cwd: Path
) -> tuple[list[_ImportOutcome], int]:
    """Import every candidate that has a selection; returns outcomes + skip count."""
    # has_selection is evaluated once per collection: it reads the CSV.
    selected = {d: has_selection(d) for d in candidates}
    skipped = [d for d in candidates if not selected[d]]
    with (
        exiftool_session() as exiftool,
        BatchProgressBar(
            total=len(candidates), description="Importing", done_description="import"
        ) as progress,
    ):
        for col_dir in skipped:
            progress.on_skipped(str(display_path(col_dir, cwd)), "no selection")
        outcomes = [
            _run_one(col_dir, gallery_dir, progress, dry_run, exiftool, cwd)
            for col_dir in candidates
            if selected[col_dir]
        ]
    return outcomes, len(skipped)


def _run_one(
    col_dir: Path,
    gallery_dir: Path,
    progress: BatchProgressBar,
    dry_run: bool,
    exiftool: ExifToolHelper | None,
    cwd: Path,
) -> _ImportOutcome:
    """Import one collection with progress reporting."""
    name = str(display_path(col_dir, cwd))
    progress.on_start(name)
    outcome = _import_one(
        col_dir, gallery_dir, dry_run=dry_run, exiftool=exiftool, cwd=cwd
    )
    progress.on_end(
        name,
        success=outcome.success,
        error_labels=(f"{len(outcome.errors)} error(s)",) if outcome.errors else (),
    )
    return outcome
