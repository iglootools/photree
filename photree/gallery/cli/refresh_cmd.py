"""``photree gallery refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clihelpers.console import err_console
from ...clihelpers.options import DRY_RUN_OPTION
from ...albums.cli.batch_ops import run_batch_refresh
from ...albums.cli.ops import resolve_check_batch_albums
from ..collection_refresh import refresh_collections
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
) -> None:
    """Refresh media metadata and collections for all albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
    run_batch_refresh(albums, display_base, dry_run=dry_run)

    # Refresh collections (implicit detection + smart materialization)
    typer.echo("\nCollections:")
    col_result = refresh_collections(resolved, dry_run=dry_run)

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
