"""``photree gallery import-all`` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clihelpers.console import err_console
from ...clihelpers.progress import StageProgressBar
from ...common.fs import display_path
from ...fsprotocol import GALLERY_YAML, LinkMode, PHOTREE_DIR, load_gallery_metadata
from ...fsprotocol import resolve_link_mode
from ..faces.face_refresh import (
    STAGE_BUILD_INDEX,
    STAGE_CLUSTER,
    STAGE_SAVE,
    STAGE_SCAN_FACE_DATA,
    refresh_face_clusters,
)
from ..importer import (
    BatchImportValidationError,
    compute_target_dir,
    validate_batch_import,
)
from .ops import (
    build_index_or_exit,
    resolve_gallery_or_exit,
    resolve_import_all_albums,
    run_batch_import,
    run_batch_post_import_check,
)


@gallery_app.command("import-all")
def import_all_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to scan for album subdirectories.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    album_dirs: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to import (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
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
    """Batch import album directories into the gallery.

    Either scan --dir for immediate subdirectories, or provide explicit
    album directories via --album-dir (repeatable). Copies each album to
    <gallery>/albums/YYYY/<album-name>/, generates missing IDs, refreshes
    JPEGs, optimizes links, and runs gallery-wide checks.
    """
    if base_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()

    albums = resolve_import_all_albums(base_dir, album_dirs)
    index = build_index_or_exit(resolved_gallery, cwd)

    try:
        validate_batch_import(albums, index, resolved_gallery)
    except BatchImportValidationError as exc:
        err_console.print(f"Cannot import — {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Found {len(albums)} album(s).\n")
    typer.echo("Import:")
    imported, failed_albums = run_batch_import(
        albums, resolved_gallery, resolved_lm, dry_run, max_workers=os.cpu_count()
    )

    if not dry_run and imported > 0:
        typer.echo("\nPost-Import Check:")
        imported_targets = [
            compute_target_dir(resolved_gallery, a.name)
            for a in albums
            if a not in failed_albums
        ]
        check_failed = run_batch_post_import_check(imported_targets, cwd)
        if check_failed:
            err_console.print("\nTo investigate failures:")
            for target_dir in check_failed:
                err_console.print(
                    f'  photree album check --album-dir "{display_path(target_dir, cwd)}"'
                )

    # Gallery-wide face clustering (once after all albums imported)
    gallery_meta = load_gallery_metadata(resolved_gallery / PHOTREE_DIR / GALLERY_YAML)
    if gallery_meta.faces_enabled and not dry_run and imported > 0:
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

    typer.echo(f"\nDone. {imported} album(s) imported, {len(failed_albums)} failed.")
    if failed_albums:
        raise typer.Exit(code=1)
