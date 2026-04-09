"""``photree gallery import`` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...fsprotocol import LinkMode
from ...fsprotocol import resolve_link_mode
from ...clihelpers.console import err_console
from ...clihelpers.progress import StageProgressBar
from ...fsprotocol import GALLERY_YAML, PHOTREE_DIR, load_gallery_metadata
from ..faces.face_refresh import (
    STAGE_BUILD_INDEX,
    STAGE_CLUSTER,
    STAGE_SAVE,
    STAGE_SCAN_FACE_DATA,
    refresh_face_clusters,
)
from .ops import (
    build_index_or_exit,
    print_single_import_result,
    resolve_gallery_or_exit,
    run_single_import,
    validate_single_import_or_exit,
)


@gallery_app.command("import")
def import_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to import into the gallery.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    link_mode: Annotated[
        LinkMode | None,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Import an existing album directory into the gallery.

    Copies the album to <gallery>/albums/YYYY/<album-name>/, generates a
    missing album ID, refreshes JPEGs if stale, optimizes links, and runs
    integrity checks.
    """
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()
    index = build_index_or_exit(resolved_gallery, cwd)

    validate_single_import_or_exit(album_dir, index, resolved_gallery, cwd)
    result = run_single_import(
        album_dir, resolved_gallery, resolved_lm, dry_run, max_workers=os.cpu_count()
    )
    print_single_import_result(result, cwd, dry_run)

    # Gallery-wide face clustering (incremental — adds new album's faces)
    gallery_meta = load_gallery_metadata(resolved_gallery / PHOTREE_DIR / GALLERY_YAML)
    if gallery_meta.faces_enabled and not dry_run:
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
            face_result = refresh_face_clusters(
                resolved_gallery,
                distance_threshold=gallery_meta.face_cluster_threshold,
                on_stage_start=progress.on_start,
                on_stage_end=progress.on_end,
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
