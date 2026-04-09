"""``photree gallery refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clihelpers.console import err_console
from ...clihelpers.options import DRY_RUN_OPTION
from ...clihelpers.progress import StageProgressBar
from ...albums.cli.batch_ops import run_batch_refresh
from ...albums.cli.ops import resolve_check_batch_albums
from ...fsprotocol import GALLERY_YAML, PHOTREE_DIR, load_gallery_metadata
from ..browsable_refresh import refresh_browsable
from ..collection_refresh import (
    STAGE_IMPLICIT_REFRESH,
    STAGE_SCAN_ALBUMS,
    STAGE_SMART_REFRESH,
    STAGE_TITLE_SYNC,
    refresh_collections,
)
from ..faces.face_refresh import (
    STAGE_BUILD_INDEX,
    STAGE_CLUSTER,
    STAGE_SAVE,
    STAGE_SCAN_FACE_DATA,
    refresh_face_clusters,
)
from .ops import resolve_gallery_or_exit


@gallery_app.command("refresh")
def refresh_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    dry_run: DRY_RUN_OPTION = False,
    redetect_faces: Annotated[
        bool,
        typer.Option(
            "--redetect-faces",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    regenerate_face_thumbs: Annotated[
        bool,
        typer.Option(
            "--regenerate-face-thumbs",
            help="Regenerate face detection thumbnails from originals.",
        ),
    ] = False,
) -> None:
    """Refresh media metadata, face data, and collections for all albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
    run_batch_refresh(
        albums,
        display_base,
        dry_run=dry_run,
        redetect_faces=redetect_faces,
        regenerate_face_thumbs=regenerate_face_thumbs,
    )

    # Face clustering (before collection refresh so cluster data is available)
    gallery_meta = load_gallery_metadata(resolved / PHOTREE_DIR / GALLERY_YAML)
    if gallery_meta.faces_enabled:
        typer.echo("\nFaces:")
        threshold = gallery_meta.face_cluster_threshold
        with StageProgressBar(
            total=4,
            labels={
                STAGE_SCAN_FACE_DATA: "Scanning face data",
                STAGE_BUILD_INDEX: "Building similarity index",
                STAGE_CLUSTER: "Clustering faces",
                STAGE_SAVE: "Saving results",
            },
        ) as face_progress:
            face_result = refresh_face_clusters(
                resolved,
                distance_threshold=threshold,
                dry_run=dry_run,
                force_full=redetect_faces,
                on_stage_start=face_progress.on_start,
                on_stage_end=face_progress.on_end,
            )

        typer.echo(
            f"  {face_result.total_faces} face(s), "
            f"{face_result.total_clusters} cluster(s) "
            f"({face_result.mode})"
        )
        if not face_result.success:
            for error in face_result.errors:
                err_console.print(f"  error: {error.message}")
            raise typer.Exit(code=1)

    # Refresh collections (implicit detection + smart materialization)
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
        col_result = refresh_collections(
            resolved,
            dry_run=dry_run,
            on_stage_start=progress.on_start,
            on_stage_end=progress.on_end,
        )

    if col_result.created:
        for name in col_result.created:
            typer.echo(f"  created: {name}")
    if col_result.updated:
        for name in col_result.updated:
            typer.echo(f"  updated: {name}")
    if col_result.renamed:
        for old, new in col_result.renamed:
            typer.echo(f"  renamed: {old} -> {new}")
    if col_result.deleted:
        for name in col_result.deleted:
            typer.echo(f"  deleted: {name}")
    if col_result.album_renames:
        typer.echo("\nAlbum title sync:")
        for old, new in col_result.album_renames:
            typer.echo(f"  {old} -> {new}")

    if not col_result.success:
        for error in col_result.errors:
            err_console.print(f"  error: {error.message}")
        raise typer.Exit(code=1)

    if not (
        col_result.created
        or col_result.updated
        or col_result.renamed
        or col_result.deleted
        or col_result.album_renames
    ):
        typer.echo("  no changes")

    # Refresh browsable directory structure
    typer.echo("\nBrowsable:")
    from rich.progress import Progress, SpinnerColumn, TextColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Rendering browsable structure...", total=None)
        browsable_result = refresh_browsable(resolved, dry_run=dry_run)

    if not browsable_result.success:
        for error in browsable_result.errors:
            err_console.print(f"  error: {error.message}")
        raise typer.Exit(code=1)

    typer.echo(
        f"  {browsable_result.albums_rendered} album(s), "
        f"{browsable_result.collections_rendered} collection(s), "
        f"{browsable_result.symlinks_created} symlink(s)"
    )
