"""``photree gallery show`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...album.store.album_discovery import discover_albums
from ...common.fs import display_path
from ...fsprotocol import PHOTREE_DIR
from ...gallery.store.metadata import load_gallery_metadata
from ...gallery.store.protocol import GALLERY_YAML
from .ops import resolve_gallery_or_exit


@gallery_app.command("show")
def show_cmd(
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
) -> None:
    """Display gallery metadata."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()
    metadata = load_gallery_metadata(resolved / PHOTREE_DIR / GALLERY_YAML)
    albums = discover_albums(resolved)

    typer.echo(f"Gallery: {display_path(resolved, cwd)}")
    typer.echo(f"  link-mode: {metadata.link_mode}")
    typer.echo(f"  albums: {len(albums)}")
