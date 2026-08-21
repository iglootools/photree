"""``photree gallery stats`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...albums.cli.batch_ops.stats import run_batch_stats
from ...albums.cli.ops import resolve_check_batch_albums
from ...clihelpers.resolution import resolve_gallery_or_exit
from ..stats import compute_gallery_stats, format_gallery_stats
from . import gallery_app


@gallery_app.command("stats")
def stats_cmd(
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Show aggregated disk usage and content statistics for all albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
    run_batch_stats(
        albums,
        display_base,
        render=lambda albums_stats: format_gallery_stats(
            compute_gallery_stats(albums_stats, resolved)
        ),
    )
