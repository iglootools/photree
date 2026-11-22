from pathlib import Path
from typing import Annotated

import typer

from photree.clihelpers.console import err_console
from photree.clihelpers.runtime import runtime_of
from photree.common.formatting import indent
from photree.common.fs import display_path
from photree.foundation.gallery_metadata import (
    GALLERY_YAML,
    GalleryMetadata,
    save_gallery_metadata,
)
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.linking import LinkMode
from photree.gallery.cli import app


@app.command("init")
def init_cmd(
    ctx: typer.Context,
    gallery_dir: Annotated[
        Path,
        typer.Option(
            "--gallery-dir",
            "-g",
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
            help="Default link mode for refresh and other link-mode operations.",
        ),
    ] = LinkMode.HARDLINK,
) -> None:
    """Initialize gallery metadata (.photree/gallery.yaml)."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    gallery_yaml = gallery_dir / PHOTREE_DIR / GALLERY_YAML
    if gallery_yaml.is_file():
        err_console.print(
            f"Gallery already initialized: {display_path(gallery_yaml, cwd)}\n"
            "Use 'photree gallery metadata set' to change settings.",
            markup=False,
        )
        raise typer.Exit(code=1)

    save_gallery_metadata(gallery_dir, GalleryMetadata(link_mode=link_mode))
    is_cwd = gallery_dir.resolve() == cwd.resolve()
    # The short gallery flag differs between commands (``-g`` for import and
    # export, ``-d`` for check and stats); the long form works for all.
    gallery_flag = (
        "" if is_cwd else f' --gallery-dir "{display_path(gallery_dir, cwd)}"'
    )
    next_steps = [
        f"photree gallery import -a <album-dir>{gallery_flag}",
        f"photree gallery check{gallery_flag}",
        f"photree gallery stats{gallery_flag}",
        f"photree gallery export --share-dir <share-dir>{gallery_flag}",
    ]
    typer.echo(
        "\n".join(
            [
                f"Created {display_path(gallery_yaml, cwd)} (link-mode: {link_mode})",
                "",
                "Next steps:",
                *(indent(step) for step in next_steps),
            ]
        )
    )
