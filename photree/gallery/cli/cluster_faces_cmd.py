"""``photree gallery cluster-faces`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...albums.batchcli.refresh import run_batch_refresh
from ...albums.batchcli.resolution import resolve_check_batch_albums
from ...clihelpers.options import DRY_RUN_OPTION
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...clihelpers.sysdeps import (
    FACE_DETECTION_DEPS,
    refresh_deps,
    require_system_deps,
)
from ...foundation.gallery_metadata import GALLERY_YAML, load_gallery_metadata
from ...foundation.layout import PHOTREE_DIR
from . import gallery_app
from .ops import require_valid_threshold, run_face_clustering


@gallery_app.command("cluster-faces")
def cluster_faces_cmd(
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
    redetect: Annotated[
        bool,
        typer.Option(
            "--redetect",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    refresh_thumbs: Annotated[
        bool,
        typer.Option(
            "--refresh-thumbs",
            help="Refresh face detection thumbnails from originals.",
        ),
    ] = False,
    threshold: Annotated[
        float | None,
        typer.Option(
            "--threshold",
            help="Cosine distance threshold for clustering (0.0-1.0). Overrides gallery.yaml.",
        ),
    ] = None,
) -> None:
    """Run face detection and clustering on all albums in the gallery."""
    # --redetect / --refresh-thumbs run a full album refresh first, which also
    # rebuilds the EXIF cache — so those flags widen the requirement set.
    require_system_deps(
        refresh_deps() if (redetect or refresh_thumbs) else FACE_DETECTION_DEPS
    )

    require_valid_threshold(threshold, "--threshold")
    resolved = resolve_gallery_or_exit(gallery_dir)

    if redetect or refresh_thumbs:
        albums, display_base = resolve_check_batch_albums(resolved, None)
        run_batch_refresh(
            albums,
            display_base,
            dry_run=dry_run,
            redetect_faces=redetect,
            refresh_face_thumbs=refresh_thumbs,
        )

    gallery_meta = load_gallery_metadata(resolved / PHOTREE_DIR / GALLERY_YAML)
    run_face_clustering(
        resolved,
        # ``is None``, not ``or``: 0.0 is a valid (strictest) threshold.
        distance_threshold=(
            gallery_meta.face_cluster_threshold if threshold is None else threshold
        ),
        dry_run=dry_run,
        force_full=redetect,
    )
