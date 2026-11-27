"""The ``photree gallery init`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.clihelpers.console import err_console
from photree.clihelpers.options import DRY_RUN_OPTION
from photree.clihelpers.paths import expand_user_path
from photree.clihelpers.resolution import format_gallery_flag
from photree.clihelpers.runtime import runtime_of
from photree.common.formatting import format_dry_run, indent
from photree.common.fs import display_path
from photree.foundation.gallery_metadata import (
    GALLERY_YAML,
    GalleryMetadata,
    save_gallery_metadata,
)
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.linking import LinkMode
from photree.gallery.cli.app import app


@app.command("init")
def init_cmd(
    ctx: typer.Context,
    gallery_dir: Annotated[
        Path,
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory.",
            file_okay=False,
            callback=expand_user_path(exists=True),
        ),
    ] = Path(),
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="Default link mode for refresh and other link-mode operations.",
        ),
    ] = LinkMode.HARDLINK,
    *,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Initialize gallery metadata (.photree/gallery.yaml)."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    gallery_yaml = gallery_dir / PHOTREE_DIR / GALLERY_YAML
    if gallery_yaml.is_file():
        err_console.print(
            f"Gallery already initialized: {display_path(gallery_yaml, cwd)}\n"
            "Use 'photree gallery metadata set"
            f"{format_gallery_flag(gallery_dir, cwd)}' to change settings.",
            markup=False,
        )
        raise typer.Exit(code=1)

    if dry_run:
        typer.echo(
            format_dry_run(
                f"Would create {display_path(gallery_yaml, cwd)} "
                f"(link-mode: {link_mode})",
                dry_run=dry_run,
            ),
        )
        raise typer.Exit(code=0)

    save_gallery_metadata(gallery_dir, GalleryMetadata(link_mode=link_mode))
    is_cwd = gallery_dir.resolve() == cwd.resolve()
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
            ],
        ),
    )
