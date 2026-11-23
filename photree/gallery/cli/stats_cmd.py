"""The ``photree gallery stats`` command."""

import typer

from photree.albums.batchcli.resolution import resolve_gallery_albums
from photree.albums.batchcli.stats import run_batch_stats
from photree.clihelpers.options import GALLERY_DIR_OPTION
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.gallery.cli.app import app
from photree.gallery.cli.stats_output import format_gallery_stats
from photree.gallery.stats import compute_gallery_stats


@app.command("stats")
def stats_cmd(
    ctx: typer.Context,
    gallery_dir: GALLERY_DIR_OPTION = None,
) -> None:
    """Show disk usage and content statistics summed over the gallery's albums."""
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    resolved = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    albums, display_base = resolve_gallery_albums(resolved)
    run_batch_stats(
        albums,
        display_base,
        render=lambda albums_stats: format_gallery_stats(
            compute_gallery_stats(albums_stats, resolved),
        ),
        cwd=cwd,
    )
