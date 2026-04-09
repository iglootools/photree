"""Shared helpers for gallery CLI commands.

Gallery-specific resolution, index building, and import stage helpers
used by gallery command modules. Extracted to keep command modules focused on
argument parsing and orchestration.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...album import (
    check as album_check,
)
from ...album.check import output as preflight_output
from ...album.check.output import format_naming_checks
from ...album.store.metadata import load_album_metadata
from ...album.id import format_album_external_id
from ...common.fs import display_path
from ...fsprotocol import LinkMode
from ...fsprotocol import resolve_gallery_dir
from .. import (
    AlbumIndex,
    MissingAlbumIdError,
    build_album_id_to_path_index,
)
from ..importer import AlbumImportResult
from ..cmd_handler.validate_import import (
    DuplicateAlbumIdError,
    NamingValidationError,
    TargetExistsError,
    validate_single_import,
)
from ..cmd_handler.importer import run_single_import as _run_single_import
from ..cmd_handler.importer import run_batch_import as _run_batch_import
from ..cmd_handler.post_import_check import (
    run_batch_post_import_check as _run_batch_post_import_check,
)
from ...clihelpers.console import console, err_console
from ...common.formatting import CHECK
from ...clihelpers.progress import BatchProgressBar, StageProgressBar


# ---------------------------------------------------------------------------
# Gallery resolution
# ---------------------------------------------------------------------------


def resolve_gallery_or_exit(gallery_dir: Path | None) -> Path:
    """Resolve gallery directory or exit with a clear error."""
    try:
        return resolve_gallery_dir(gallery_dir)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc


def build_index_or_exit(gallery_dir: Path, cwd: Path) -> AlbumIndex:
    """Build the gallery album index, or exit on missing IDs."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Building album index...", total=None)
            return build_album_id_to_path_index(gallery_dir)
    except MissingAlbumIdError as exc:
        err_console.print("Albums with missing IDs found:")
        for p in exc.albums:
            err_console.print(f"  {display_path(p, cwd)}")
        err_console.print(
            "\nRun 'photree gallery fix --id' to generate missing album IDs."
        )
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# Single album import helpers
# ---------------------------------------------------------------------------


def validate_single_import_or_exit(
    album_dir: Path,
    index: AlbumIndex,
    gallery_dir: Path,
    cwd: Path,
) -> None:
    """Validate a single album before import, or exit with an error."""
    try:
        validate_single_import(album_dir, index, gallery_dir)
    except DuplicateAlbumIdError as exc:
        err_console.print(
            f"Cannot import — album ID already exists in gallery:\n"
            f"  source: {display_path(exc.source, cwd)}\n"
            f"  existing: {display_path(exc.existing, cwd)}\n"
            f"  id: {format_album_external_id(exc.album_id)}"
        )
        raise typer.Exit(code=1) from exc
    except NamingValidationError as exc:
        typer.echo("Naming Convention Check:")
        console.print(format_naming_checks(exc.naming_result))
        err_console.print(
            "\nAlbum name does not follow naming conventions. "
            "Rename the album directory before importing."
        )
        raise typer.Exit(code=1) from exc
    except TargetExistsError as exc:
        err_console.print(
            f"Target already exists: {display_path(exc.target, cwd)}\n"
            "Cannot import — an album with the same name is already in the gallery."
        )
        raise typer.Exit(code=1) from exc


def run_single_import(
    album_dir: Path,
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    max_workers: int | None = None,
) -> AlbumImportResult:
    """Execute a single album import with stage progress bar."""
    typer.echo("Import:")
    with StageProgressBar(
        total=5,
        labels={
            "copy": "Copying album",
            "id": "Checking album ID",
            "jpeg": "Refreshing JPEGs",
            "optimize": "Optimizing links",
            "refresh-derived": "Refreshing media IDs, EXIF cache, faces",
        },
    ) as progress:
        try:
            result = _run_single_import(
                album_dir,
                gallery_dir,
                link_mode,
                dry_run,
                on_stage_start=progress.on_start,
                on_stage_end=progress.on_end,
                max_workers=max_workers,
            )
        except ValueError as exc:
            err_console.print(str(exc))
            raise typer.Exit(code=1) from exc
    return result


def print_single_import_result(
    result: AlbumImportResult,
    cwd: Path,
    dry_run: bool,
) -> None:
    """Display import result and run post-import preflight check."""
    if not dry_run:
        meta = load_album_metadata(result.target_dir)
        if meta is not None:
            typer.echo(f"Album ID: {format_album_external_id(meta.id)}")
    typer.echo(f"Target: {display_path(result.target_dir, cwd)}")

    if not dry_run:
        typer.echo("\nPost-Import Check:")
        check_result = album_check.run_album_preflight(result.target_dir)
        console.print(preflight_output.format_album_preflight_checks(check_result))
        if not check_result.success:
            err_console.print(
                f'\nTo investigate: photree album check --album-dir "{display_path(result.target_dir, cwd)}"'
            )
            raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Batch import helpers
# ---------------------------------------------------------------------------


def resolve_import_all_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> list[Path]:
    """Resolve album list for batch import from --dir or --album-dir."""
    if album_dirs is not None:
        return album_dirs

    scan_dir = base_dir if base_dir is not None else Path(".").resolve()
    albums = sorted(p for p in scan_dir.iterdir() if p.is_dir())
    if not albums:
        typer.echo("No album directories found.")
        raise typer.Exit(code=0)
    return albums


def run_batch_import(
    albums: list[Path],
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    max_workers: int | None = None,
) -> tuple[int, list[Path]]:
    """Execute batch import with progress bar.

    Returns ``(imported_count, failed_albums)``.
    """
    with BatchProgressBar(
        total=len(albums), description="Importing", done_description="import"
    ) as progress:
        result = _run_batch_import(
            albums,
            gallery_dir,
            link_mode,
            dry_run,
            max_workers=max_workers,
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    return result.imported, result.failed_albums


def run_batch_post_import_check(
    imported_targets: list[Path],
    cwd: Path,
) -> list[Path]:
    """Run post-import checks on all imported albums.

    Returns the list of albums that failed checking.
    """
    with BatchProgressBar(
        total=len(imported_targets),
        description="Checking",
        done_description="check",
    ) as check_progress:
        check_failed = _run_batch_post_import_check(
            imported_targets,
            display_fn=lambda p: str(display_path(p, cwd)),
            on_start=check_progress.on_start,
            on_end=lambda name, success, errors: check_progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    return check_failed


# ---------------------------------------------------------------------------
# Face clustering helper
# ---------------------------------------------------------------------------


def run_face_clustering(
    gallery_dir: Path,
    *,
    distance_threshold: float | None = None,
    dry_run: bool = False,
    force_full: bool = False,
) -> None:
    """Run gallery-wide face clustering with progress bar and output.

    Raises :class:`typer.Exit` on clustering errors.
    """
    from ..faces.face_refresh import (
        STAGE_BUILD_INDEX,
        STAGE_CLUSTER,
        STAGE_SAVE,
        STAGE_SCAN_FACE_DATA,
        refresh_face_clusters,
    )

    typer.echo("\nFace clustering:")
    with StageProgressBar(
        total=4,
        labels={
            STAGE_SCAN_FACE_DATA: "Scanning face data",
            STAGE_BUILD_INDEX: "Building similarity index",
            STAGE_CLUSTER: "Clustering faces",
            STAGE_SAVE: "Saving results",
        },
    ) as progress:
        result = refresh_face_clusters(
            gallery_dir,
            distance_threshold=distance_threshold,
            dry_run=dry_run,
            force_full=force_full,
            on_stage_start=progress.on_start,
            on_stage_end=progress.on_end,
        )

    match result.mode:
        case "none":
            console.print(
                f"{CHECK} face clustering (no changes —"
                f" {result.total_faces} face(s),"
                f" {result.total_clusters} cluster(s))"
            )
        case _:
            console.print(
                f"{CHECK} face clustering"
                f" ({result.total_faces} face(s),"
                f" {result.total_clusters} cluster(s),"
                f" {result.mode})"
            )

    if not result.success:
        for error in result.errors:
            err_console.print(f"  error: {error.message}")
        raise typer.Exit(code=1)
