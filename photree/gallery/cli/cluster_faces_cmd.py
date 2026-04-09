"""``photree gallery cluster-faces`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clihelpers.console import err_console
from ...clihelpers.options import DRY_RUN_OPTION
from ...clihelpers.progress import StageProgressBar
from ...fsprotocol import GALLERY_YAML, PHOTREE_DIR, load_gallery_metadata
from ..faces.face_refresh import (
    STAGE_BUILD_INDEX,
    STAGE_CLUSTER,
    STAGE_SAVE,
    STAGE_SCAN_FACE_DATA,
    refresh_face_clusters,
)
from .ops import resolve_gallery_or_exit


@gallery_app.command("cluster-faces")
def cluster_faces_cmd(
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
    redetect: Annotated[
        bool,
        typer.Option(
            "--redetect",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    regenerate_thumbs: Annotated[
        bool,
        typer.Option(
            "--regenerate-thumbs",
            help="Regenerate face detection thumbnails from originals.",
        ),
    ] = False,
    threshold: Annotated[
        Optional[float],
        typer.Option(
            "--threshold",
            help="Cosine distance threshold for clustering (0.0-1.0). Overrides gallery.yaml.",
        ),
    ] = None,
) -> None:
    """Run face detection and clustering on all albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)

    # Run album-level face detection first (batch)
    if redetect or regenerate_thumbs:
        from ...albums.cli.batch_ops import run_batch_refresh
        from ...albums.cli.ops import resolve_check_batch_albums

        albums, display_base = resolve_check_batch_albums(resolved, None)
        run_batch_refresh(
            albums,
            display_base,
            dry_run=dry_run,
            redetect_faces=redetect,
            regenerate_face_thumbs=regenerate_thumbs,
        )

    # Gallery-level clustering
    gallery_meta = load_gallery_metadata(resolved / PHOTREE_DIR / GALLERY_YAML)
    distance_threshold = threshold or gallery_meta.face_cluster_threshold

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
            resolved,
            distance_threshold=distance_threshold,
            dry_run=dry_run,
            force_full=redetect,
            on_stage_start=progress.on_start,
            on_stage_end=progress.on_end,
        )

    typer.echo(
        f"  {result.total_faces} face(s), "
        f"{result.total_clusters} cluster(s) "
        f"({result.mode})"
    )

    if not result.success:
        for error in result.errors:
            err_console.print(f"  error: {error.message}")
        raise typer.Exit(code=1)
