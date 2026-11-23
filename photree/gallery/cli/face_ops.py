"""Gallery-wide face clustering for gallery commands, and its option check."""

from pathlib import Path

import typer

from photree.clihelpers.console import console
from photree.clihelpers.progress import StageProgressBar
from photree.clihelpers.usage import invalid_value_error
from photree.common.formatting import CHECK, format_dry_run
from photree.gallery.faces.face_refresh import (
    STAGE_BUILD_INDEX,
    STAGE_CLUSTER,
    STAGE_SAVE,
    STAGE_SCAN_FACE_DATA,
    GalleryFaceRefreshResult,
    refresh_face_clusters,
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
