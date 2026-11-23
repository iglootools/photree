"""
Shared helpers for gallery CLI commands.

Gallery-specific resolution, index building, and import stage helpers
used by gallery command modules. Extracted to keep command modules focused on
argument parsing and orchestration.
"""

from pathlib import Path

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from photree.album import check as album_check
from photree.album.check import output as preflight_output
from photree.album.id import format_album_external_id
from photree.album.store.album_discovery import discover_potential_albums
from photree.album.store.metadata import load_album_metadata
from photree.albums.output import format_missing_ids_report
from photree.clihelpers.console import console, err_console
from photree.clihelpers.progress import BatchProgressBar, StageProgressBar
from photree.clihelpers.usage import invalid_value_error
from photree.common.exif import exiftool_session
from photree.common.formatting import CHECK, format_dry_run
from photree.common.fs import display_path
from photree.common.sysdeps import WhichFn
from photree.foundation.gallery_metadata import resolve_link_mode
from photree.foundation.linking import LinkMode
from photree.gallery import (
    AlbumIndex,
    MissingAlbumIdError,
    build_album_id_to_path_index,
)
from photree.gallery.cmd_handler.importer import BatchImportResult
from photree.gallery.cmd_handler.importer import run_batch_import as _run_batch_import
from photree.gallery.cmd_handler.importer import run_single_import as _run_single_import
from photree.gallery.cmd_handler.post_import_check import (
    run_batch_post_import_check as _run_batch_post_import_check,
)
from photree.gallery.faces.face_refresh import (
    STAGE_BUILD_INDEX,
    STAGE_CLUSTER,
    STAGE_SAVE,
    STAGE_SCAN_FACE_DATA,
    GalleryFaceRefreshResult,
    refresh_face_clusters,
)
from photree.gallery.import_plan import (
    AlbumPlan,
    GalleryImportPlan,
    ImportAction,
    plan_imports,
)
from photree.gallery.importer import AlbumImportResult
from photree.gallery.output import (
    format_import_error,
    format_import_errors,
    format_import_failure_labels,
    format_skipped,
)


def build_index_or_exit(gallery_dir: Path, cwd: Path) -> AlbumIndex:
    """Build the gallery album index, or exit on missing IDs."""
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Building album index...", total=None)
            return build_album_id_to_path_index(gallery_dir)
    except MissingAlbumIdError as exc:
        err_console.print(
            format_missing_ids_report(exc.albums, "photree gallery fix --id", cwd),
            markup=False,
        )
        raise typer.Exit(code=1) from exc


def plan_imports_or_exit(
    albums: list[Path],
    index: AlbumIndex,
    gallery_dir: Path,
    cwd: Path,
    *,
    reimport: bool,
) -> GalleryImportPlan:
    """Plan a gallery import; exit 1 if any album fails pre-import validation."""
    plan = plan_imports(albums, index, gallery_dir, reimport=reimport)
    if plan.has_errors:
        err_console.print(format_import_errors(plan, cwd))
        raise typer.Exit(code=1)
    return plan


def render_skipped(plans: list[AlbumPlan], cwd: Path) -> None:
    """Print the albums skipped as already imported and a blank line, if any."""
    if not plans:
        return
    console.print(format_skipped(plans, cwd))
    typer.echo("")


def _stage_labels(plan: AlbumPlan) -> dict[str, str]:
    copy_label = (
        "Replacing media" if plan.action is ImportAction.REIMPORT else "Copying album"
    )
    return {
        "copy": copy_label,
        "id": "Checking album ID",
        "refresh-derived": "Refreshing derived data",
    }


def run_single_import(
    plan: AlbumPlan,
    gallery_dir: Path,
    link_mode: LinkMode,
    *,
    dry_run: bool,
    max_workers: int | None = None,
    which: WhichFn,
    cwd: Path,
) -> AlbumImportResult:
    """Execute a single album import/reimport with stage progress bar."""
    typer.echo(
        format_dry_run(
            "Reimport:" if plan.action is ImportAction.REIMPORT else "Import:",
            dry_run=dry_run,
        ),
    )
    with StageProgressBar(total=3, labels=_stage_labels(plan)) as progress:
        try:
            result = _run_single_import(
                plan,
                gallery_dir,
                link_mode,
                dry_run=dry_run,
                on_stage_start=progress.on_start,
                on_stage_end=progress.on_end,
                max_workers=max_workers,
                which=which,
            )
        except (ValueError, OSError) as exc:
            # Same failure set as the batch import: the importer removes its
            # staging copy, so nothing was placed in the gallery.
            err_console.print(format_import_error(exc, cwd), markup=False)
            raise typer.Exit(code=1) from exc
    return result


def print_single_import_result(
    result: AlbumImportResult,
    cwd: Path,
    *,
    dry_run: bool,
    which: WhichFn,
) -> None:
    """Display import result and run post-import preflight check."""
    if not dry_run:
        meta = load_album_metadata(result.target_dir)
        if meta is not None:
            typer.echo(f"Album ID: {format_album_external_id(meta.id)}")
    typer.echo(f"Target: {display_path(result.target_dir, cwd)}")

    if not result.complete:
        err_console.print(
            "The album imported, but its derived data is incomplete:\n"
            + preflight_output.derived_failures_report(
                result.jpeg_failures,
                result.face_failures,
                str(display_path(result.target_dir, cwd)),
            ),
        )
        raise typer.Exit(code=1)

    if not dry_run:
        _post_import_check(result.target_dir, cwd, which=which)


def _post_import_check(target_dir: Path, cwd: Path, *, which: WhichFn) -> None:
    """Run the preflight check on a freshly imported album; exit 1 on failure."""
    typer.echo("\nPost-Import Check:")
    with exiftool_session(which=which) as exiftool:
        check_result = album_check.run_album_check(
            target_dir,
            # The import gate (import_deps) already required sips.
            sips_available=True,
            exiftool=exiftool,
            link_mode=resolve_link_mode(None, target_dir),
        )
    console.print(preflight_output.format_album_preflight_checks(check_result))
    if not check_result.success:
        err_console.print(
            "\nTo investigate, run 'photree album check --album-dir "
            f'"{display_path(target_dir, cwd)}"\'.',
            markup=False,
        )
        raise typer.Exit(code=1)


def resolve_import_all_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    *,
    cwd: Path,
) -> tuple[list[Path], list[Path]]:
    """
    Resolve album list for batch import from --dir or --album-dir.

    Returns ``(albums, skipped)``. When --dir is used, the scan is
    recursive: *albums* are directories with at least one media source,
    and *skipped* are non-album directories traversed during the walk.
    When --album-dir is used, *skipped* is always empty — the user picked
    those directories explicitly.
    """
    if album_dirs is not None:
        return (album_dirs, [])

    scan_dir = base_dir if base_dir is not None else cwd
    return discover_potential_albums(scan_dir)


def run_batch_import(
    plans: list[AlbumPlan],
    gallery_dir: Path,
    link_mode: LinkMode,
    *,
    dry_run: bool,
    max_workers: int | None = None,
    which: WhichFn,
    cwd: Path,
) -> BatchImportResult:
    """Execute batch import/reimport with progress bar."""
    with BatchProgressBar(
        total=len(plans),
        description="Importing",
        done_description="import",
    ) as progress:
        return _run_batch_import(
            plans,
            gallery_dir,
            link_mode,
            dry_run=dry_run,
            max_workers=max_workers,
            which=which,
            on_start=progress.on_start,
            on_end=lambda name, failure: progress.on_end(
                name,
                success=failure is None,
                error_labels=(
                    format_import_failure_labels(failure, cwd) if failure else ()
                ),
            ),
        )


def run_batch_post_import_check(
    imported_targets: list[Path],
    gallery_dir: Path,
    cwd: Path,
    *,
    which: WhichFn,
) -> list[Path]:
    """
    Run post-import checks on all imported albums.

    The albums are checked against the gallery's configured link mode (not a
    ``--link-mode`` override given to the import). Returns the list of albums
    that failed checking.
    """
    with BatchProgressBar(
        total=len(imported_targets),
        description="Checking",
        done_description="check",
    ) as check_progress:
        return _run_batch_post_import_check(
            imported_targets,
            link_mode=resolve_link_mode(None, gallery_dir),
            # The import gate (import_deps) already required sips.
            sips_available=True,
            which=which,
            display_fn=lambda p: str(display_path(p, cwd)),
            on_start=check_progress.on_start,
            on_end=check_progress.on_end,
        )


def require_valid_threshold(threshold: float | None, option: str) -> None:
    """Usage error unless *threshold* is unset or a cosine distance in [0.0, 1.0]."""
    if threshold is not None and not 0.0 <= threshold <= 1.0:
        raise invalid_value_error(
            name=option,
            value=threshold,
            expected="a cosine distance between 0.0 and 1.0 (lower = stricter)",
            command="gallery metadata set",
        )


def run_face_clustering(
    gallery_dir: Path,
    *,
    distance_threshold: float | None = None,
    dry_run: bool = False,
    force_full: bool = False,
) -> None:
    """Run gallery-wide face clustering with progress bar and output."""
    typer.echo(format_dry_run("\nFace clustering:", dry_run=dry_run))
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

    console.print(_face_clustering_line(result))


def _face_clustering_line(result: GalleryFaceRefreshResult) -> str:
    counts = f"{result.total_faces} face(s), {result.total_clusters} cluster(s)"
    # Compared by value so this module needs no runtime import of face_refresh,
    # which pulls in faiss and scikit-learn.
    return (
        f"{CHECK} face clustering (no changes — {counts})"
        if result.mode == "none"
        else f"{CHECK} face clustering ({counts}, {result.mode})"
    )
