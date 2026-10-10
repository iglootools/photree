"""``photree gallery show`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...album.store.album_discovery import discover_albums
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...common.formatting import indent
from ...common.fs import display_path
from ...foundation.gallery_metadata import GALLERY_YAML, load_gallery_metadata
from ...foundation.layout import ALBUMS_DIR, PHOTREE_DIR
from . import gallery_app


@gallery_app.command("show")
def show_cmd(
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
) -> None:
    """Display gallery metadata."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()
    metadata = load_gallery_metadata(resolved / PHOTREE_DIR / GALLERY_YAML)
    albums = discover_albums(resolved / ALBUMS_DIR)

    typer.echo(
        "\n".join(
            [
                f"Gallery: {display_path(resolved, cwd)}",
                indent(f"link-mode: {metadata.link_mode}"),
                indent(f"albums: {len(albums)}"),
            ]
        )
    )
