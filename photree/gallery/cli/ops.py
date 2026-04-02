"""Shared helpers for gallery CLI commands.

Gallery-specific resolution, index building, and import stage helpers
used by gallery command modules. Extracted to keep command modules focused on
argument parsing and orchestration.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...album import (
    preflight as album_preflight,
)
from ...album.preflight import output as preflight_output
from ...common.exif import try_start_exiftool
from ...album.naming import (
    AlbumNamingResult,
    check_album_naming,
    parse_album_name,
)
from ...album.preflight.output import format_naming_checks
from ...fs import (
    LinkMode,
    display_path,
    format_album_external_id,
    load_album_metadata,
    resolve_gallery_dir,
)
from .. import (
    AlbumIndex,
    MissingAlbumIdError,
    build_album_id_to_path_index,
)
from ..importer import (
    AlbumImportResult,
    compute_target_dir,
)
from .. import importer as gallery_importer
from ...clicommons.console import console, err_console
from ...clicommons.progress import BatchProgressBar, StageProgressBar


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


def validate_single_import(
    album_dir: Path,
    index: AlbumIndex,
    gallery_dir: Path,
    cwd: Path,
) -> None:
    """Validate a single album before import.

    Checks source album ID uniqueness, naming conventions, and that the
    target directory does not already exist.
    """
    # Check source album ID uniqueness against gallery
    source_meta = load_album_metadata(album_dir)
    if source_meta is not None and source_meta.id in index.id_to_path:
        existing = index.id_to_path[source_meta.id]
        err_console.print(
            f"Cannot import — album ID already exists in gallery:\n"
            f"  source: {display_path(album_dir, cwd)}\n"
            f"  existing: {display_path(existing, cwd)}\n"
            f"  id: {format_album_external_id(source_meta.id)}"
        )
        raise typer.Exit(code=1)

    # Validate album name
    naming_issues = check_album_naming(album_dir.name)
    if naming_issues:
        parsed = parse_album_name(album_dir.name)
        naming_result = AlbumNamingResult(
            parsed=parsed, issues=naming_issues, exif_check=None
        )
        typer.echo("Naming Convention Check:")
        console.print(format_naming_checks(naming_result))
        err_console.print(
            "\nAlbum name does not follow naming conventions. "
            "Rename the album directory before importing."
        )
        raise typer.Exit(code=1)

    # Check target doesn't exist
    target = compute_target_dir(gallery_dir, album_dir.name)
    if target.exists():
        err_console.print(
            f"Target already exists: {display_path(target, cwd)}\n"
            "Cannot import — an album with the same name is already in the gallery."
        )
        raise typer.Exit(code=1)


def run_single_import(
    album_dir: Path,
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
) -> AlbumImportResult:
    """Execute a single album import with stage progress bar."""
    typer.echo("Import:")
    progress = StageProgressBar(
        total=4,
        labels={
            "copy": "Copying album",
            "id": "Checking album ID",
            "jpeg": "Refreshing JPEGs",
            "optimize": "Optimizing links",
        },
    )
    try:
        result = gallery_importer.import_album(
            source_dir=album_dir,
            gallery_dir=gallery_dir,
            link_mode=link_mode,
            dry_run=dry_run,
            on_stage_start=progress.on_start,
            on_stage_end=progress.on_end,
        )
    except ValueError as exc:
        progress.stop()
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        progress.stop()
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
        check_result = album_preflight.run_album_preflight(result.target_dir)
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
) -> tuple[int, list[Path]]:
    """Execute batch import with progress bar.

    Returns ``(imported_count, failed_albums)``.
    """
    progress = BatchProgressBar(
        total=len(albums), description="Importing", done_description="import"
    )
    imported = 0
    failed: list[Path] = []

    for album_path in albums:
        album_name = album_path.name
        progress.on_start(album_name)
        try:
            gallery_importer.import_album(
                source_dir=album_path,
                gallery_dir=gallery_dir,
                link_mode=link_mode,
                dry_run=dry_run,
            )
            progress.on_end(album_name, success=True)
            imported += 1
        except (ValueError, OSError) as exc:
            progress.on_end(album_name, success=False, error_labels=(str(exc)[:60],))
            failed.append(album_path)

    progress.stop()
    return imported, failed


def run_batch_post_import_check(
    imported_targets: list[Path],
    cwd: Path,
) -> list[Path]:
    """Run post-import checks on all imported albums.

    Returns the list of albums that failed checking.
    """
    sips_available = album_preflight.check_sips_available()
    exiftool = try_start_exiftool()
    check_progress = BatchProgressBar(
        total=len(imported_targets),
        description="Checking",
        done_description="check",
    )
    check_failed: list[Path] = []
    try:
        for target_dir in imported_targets:
            target_name = display_path(target_dir, cwd)
            check_progress.on_start(str(target_name))
            check_result = album_preflight.run_album_check(
                target_dir,
                sips_available=sips_available,
                exiftool=exiftool,
            )
            if check_result.success:
                check_progress.on_end(str(target_name), success=True)
            else:
                check_progress.on_end(
                    str(target_name),
                    success=False,
                    error_labels=check_result.error_labels,
                )
                check_failed.append(target_dir)
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)
    check_progress.stop()
    return check_failed
