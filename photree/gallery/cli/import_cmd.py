"""``photree gallery import`` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...fsprotocol import GALLERY_YAML, LinkMode, PHOTREE_DIR, load_gallery_metadata
from ...fsprotocol import resolve_link_mode
from .ops import (
    build_index_or_exit,
    print_single_import_result,
    resolve_gallery_or_exit,
    run_face_clustering,
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
    """Import an existing album directory into the gallery."""
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()
    index = build_index_or_exit(resolved_gallery, cwd)

    validate_single_import_or_exit(album_dir, index, resolved_gallery, cwd)
    result = run_single_import(
        album_dir, resolved_gallery, resolved_lm, dry_run, max_workers=os.cpu_count()
    )
    print_single_import_result(result, cwd, dry_run)

    gallery_meta = load_gallery_metadata(resolved_gallery / PHOTREE_DIR / GALLERY_YAML)
    if gallery_meta.faces_enabled and not dry_run:
        run_face_clustering(
            resolved_gallery,
            distance_threshold=gallery_meta.face_cluster_threshold,
        )
