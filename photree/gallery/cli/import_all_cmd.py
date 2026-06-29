"""``photree gallery import-all`` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clihelpers.console import err_console
from ...clihelpers.options import REIMPORT_OPTION
from ...common.fs import display_path
from ...fsprotocol import GALLERY_YAML, LinkMode, PHOTREE_DIR, load_gallery_metadata
from ...fsprotocol import resolve_link_mode
from .ops import (
    build_index_or_exit,
    plan_imports_or_exit,
    render_skipped,
    resolve_gallery_or_exit,
    resolve_import_all_albums,
    run_batch_import,
    run_batch_post_import_check,
    run_face_clustering,
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
    reimport: REIMPORT_OPTION = False,
) -> None:
    """Batch import album directories into the gallery.

    Either scan --dir for immediate subdirectories, or provide explicit
    album directories via --album-dir (repeatable). Copies each album to
    <gallery>/albums/YYYY/<album-name>/, generates missing IDs, refreshes
    JPEGs, and runs gallery-wide checks. Already-imported albums are skipped
    unless --reimport is given.
    """
    if base_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()

    albums, non_albums = resolve_import_all_albums(base_dir, album_dirs)

    if non_albums:
        typer.echo(f"Skipped {len(non_albums)} non-album director(ies):")
        for s in non_albums:
            typer.echo(f"  {display_path(s, cwd)}")
        typer.echo("")

    if not albums:
        typer.echo("No album directories found.")
        raise typer.Exit(code=0)

    index = build_index_or_exit(resolved_gallery, cwd)

    import_plan = plan_imports_or_exit(
        albums, index, resolved_gallery, cwd, reimport=reimport
    )

    if import_plan.skipped:
        render_skipped(import_plan.skipped, cwd)

    to_import = import_plan.to_import
    if not to_import:
        typer.echo("Nothing to import.")
        raise typer.Exit(code=0)

    typer.echo(f"Found {len(to_import)} album(s).\n")
    typer.echo("Import:")
    imported, failed_sources = run_batch_import(
        to_import, resolved_gallery, resolved_lm, dry_run, max_workers=os.cpu_count()
    )

    if not dry_run and imported > 0:
        typer.echo("\nPost-Import Check:")
        imported_targets = [
            plan.target for plan in to_import if plan.source not in failed_sources
        ]
        check_failed = run_batch_post_import_check(imported_targets, cwd)
        if check_failed:
            err_console.print("\nTo investigate failures:")
            for target_dir in check_failed:
                err_console.print(
                    f'  photree album check --album-dir "{display_path(target_dir, cwd)}"'
                )

    gallery_meta = load_gallery_metadata(resolved_gallery / PHOTREE_DIR / GALLERY_YAML)
    if gallery_meta.faces_enabled and not dry_run and imported > 0:
        run_face_clustering(
            resolved_gallery,
            distance_threshold=gallery_meta.face_cluster_threshold,
        )

    skipped_note = (
        f", {len(import_plan.skipped)} skipped" if import_plan.skipped else ""
    )
    typer.echo(
        f"\nDone. {imported} album(s) imported, "
        f"{len(failed_sources)} failed{skipped_note}."
    )
    if failed_sources:
        raise typer.Exit(code=1)
