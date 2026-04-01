"""``photree gallery optimize`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...clicommons.options import (
    CHECK_BEFORE_OPTION,
    CHECKSUM_OPTION,
    DRY_RUN_OPTION,
    LINK_MODE_OPTION,
)
from ...albums.cli.batch_ops import resolve_batch_albums, run_batch_optimize
from ...fs import resolve_link_mode
from .ops import resolve_gallery_or_exit


@gallery_app.command("optimize")
def optimize_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    link_mode: LINK_MODE_OPTION = None,
    check: CHECK_BEFORE_OPTION = True,
    checksum: CHECKSUM_OPTION = True,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Optimize all iOS albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_batch_albums(resolved, None)
    run_batch_optimize(
        albums,
        display_base,
        link_mode=resolve_link_mode(link_mode, resolved),
        check=check,
        checksum=checksum,
        dry_run=dry_run,
    )
