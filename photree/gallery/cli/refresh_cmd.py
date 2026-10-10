"""``photree gallery refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...albums.batchcli.refresh import run_batch_refresh
from ...albums.batchcli.resolution import resolve_check_batch_albums
from ...clihelpers.console import console, err_console
from ...clihelpers.options import DRY_RUN_OPTION
from ...clihelpers.progress import StageProgressBar, run_with_spinner
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...clihelpers.sysdeps import refresh_deps, require_system_deps
from ...common.formatting import CHECK, indent
from ...foundation.gallery_metadata import GALLERY_YAML, load_gallery_metadata
from ...foundation.layout import PHOTREE_DIR
from ..browsable_refresh import refresh_browsable as refresh_gallery_browsable
from ..collection_refresh import (
    STAGE_IMPLICIT_REFRESH,
    STAGE_SCAN_ALBUMS,
    STAGE_SMART_REFRESH,
    STAGE_TITLE_SYNC,
    refresh_collections,
)
from . import gallery_app
from .ops import run_face_clustering
from .refresh_output import (
    format_browsable_error,
    format_collection_changes,
    format_collection_refresh_error,
    format_dangling_members,
)


@gallery_app.command("refresh")
def refresh_cmd(
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
    dry_run: DRY_RUN_OPTION = False,
    refresh_browsable: Annotated[
        bool,
        typer.Option(
            "--refresh-browsable",
            help="Force rebuild all browsable directories (skip check gate).",
        ),
    ] = False,
    refresh_jpeg: Annotated[
        bool,
        typer.Option(
            "--refresh-jpeg",
            help="Force rebuild all JPEG directories (skip check gate).",
        ),
    ] = False,
    refresh_exif_cache: Annotated[
        bool,
        typer.Option(
            "--refresh-exif-cache",
            help="Force re-read all EXIF timestamps.",
        ),
    ] = False,
    redetect_faces: Annotated[
        bool,
        typer.Option(
            "--redetect-faces",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    refresh_face_thumbs: Annotated[
        bool,
        typer.Option(
            "--refresh-face-thumbs",
            help="Refresh face detection thumbnails from originals.",
        ),
    ] = False,
) -> None:
    """Refresh all derived data, face clusters, and collections for the gallery."""
    require_system_deps(refresh_deps())

    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()
    albums, display_base = resolve_check_batch_albums(resolved, None)
    run_batch_refresh(
        albums,
        display_base,
        dry_run=dry_run,
        force_browsable=refresh_browsable,
        force_jpeg=refresh_jpeg,
        force_exif_cache=refresh_exif_cache,
        redetect_faces=redetect_faces,
        refresh_face_thumbs=refresh_face_thumbs,
    )
    # Face clustering runs before the collection refresh so cluster data is
    # available to it.
    _refresh_face_clusters(resolved, dry_run=dry_run, force_full=redetect_faces)
    _refresh_collections(resolved, cwd, dry_run=dry_run)
    _refresh_browsable(resolved, cwd, dry_run=dry_run)


def _refresh_face_clusters(
    gallery_dir: Path, *, dry_run: bool, force_full: bool
) -> None:
    gallery_meta = load_gallery_metadata(gallery_dir / PHOTREE_DIR / GALLERY_YAML)
    if gallery_meta.faces_enabled:
        run_face_clustering(
            gallery_dir,
            distance_threshold=gallery_meta.face_cluster_threshold,
            dry_run=dry_run,
            force_full=force_full,
        )


def _refresh_collections(gallery_dir: Path, cwd: Path, *, dry_run: bool) -> None:
    """Implicit detection + smart materialization; exit 1 on any error."""
    typer.echo("\nCollections:")
    with StageProgressBar(
        total=4,
        labels={
            STAGE_SCAN_ALBUMS: "Scanning albums",
            STAGE_TITLE_SYNC: "Syncing album titles",
            STAGE_IMPLICIT_REFRESH: "Refreshing implicit collections",
            STAGE_SMART_REFRESH: "Refreshing smart collections",
        },
    ) as progress:
        result = refresh_collections(
            gallery_dir,
            dry_run=dry_run,
            on_stage_start=progress.on_start,
            on_stage_end=progress.on_end,
        )

    # Report what was applied even on failure: a later stage's error does
    # not undo an earlier stage's changes.
    typer.echo(indent("\n".join(format_collection_changes(result))))
    if not result.success:
        err_console.print(
            "\n".join(
                indent(format_collection_refresh_error(error, cwd))
                for error in result.errors
            ),
            markup=False,
        )
        raise typer.Exit(code=1)


def _refresh_browsable(gallery_dir: Path, cwd: Path, *, dry_run: bool) -> None:
    """Re-render the browsable/ tree; exit 1 on any error."""
    typer.echo("\nBrowsable:")
    result = run_with_spinner(
        "Rendering browsable structure...",
        lambda: refresh_gallery_browsable(gallery_dir, dry_run=dry_run),
    )
    if result.dangling_members:
        err_console.print(
            indent(format_dangling_members(result.dangling_members, cwd)), markup=False
        )
    if not result.success:
        err_console.print(
            "\n".join(indent(format_browsable_error(e, cwd)) for e in result.errors),
            markup=False,
        )
        raise typer.Exit(code=1)

    console.print(
        f"{CHECK} browsable "
        f"({result.albums_rendered} album(s), "
        f"{result.collections_rendered} collection(s), "
        f"{result.symlinks_created} symlink(s))"
    )
