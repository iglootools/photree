"""``photree gallery init`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import gallery_app
from ...fs import (
    GALLERY_YAML,
    GalleryMetadata,
    LinkMode,
    PHOTREE_DIR,
    display_path,
    save_gallery_metadata,
)


@gallery_app.command("init")
def init_cmd(
    gallery_dir: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="Default link mode for optimize and other link-mode operations.",
        ),
    ] = LinkMode.HARDLINK,
) -> None:
    """Initialize gallery metadata (.photree/gallery.yaml)."""
    gallery_yaml = gallery_dir / PHOTREE_DIR / GALLERY_YAML
    if gallery_yaml.is_file():
        typer.echo(
            f"Gallery already initialized: {display_path(gallery_yaml, Path.cwd())}\n"
            "Edit the file directly to change settings.",
            err=True,
        )
        raise typer.Exit(code=1)

    save_gallery_metadata(gallery_dir, GalleryMetadata(link_mode=link_mode))
    cwd = Path.cwd()
    is_cwd = gallery_dir.resolve() == cwd.resolve()
    gallery_flag = "" if is_cwd else f' -g "{display_path(gallery_dir, cwd)}"'
    typer.echo(
        f"Created {display_path(gallery_yaml, cwd)} (link-mode: {link_mode})\n"
        "\nNext steps:\n"
        f"  photree gallery import -a <album-dir>{gallery_flag}\n"
        f"  photree gallery check{gallery_flag}\n"
        f"  photree gallery stats{gallery_flag}\n"
        f"  photree gallery export --share-dir <share-dir>{gallery_flag}"
    )
