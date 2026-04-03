"""``photree gallery refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clihelpers.options import DRY_RUN_OPTION
from ...albums.cli.batch_ops import resolve_check_batch_albums, run_batch_refresh
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
    """Refresh media metadata (.photree/media.yaml) for all albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
    run_batch_refresh(albums, display_base, dry_run=dry_run)
