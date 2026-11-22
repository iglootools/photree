"""``albums init`` wrapper."""

from pathlib import Path

import typer

from photree.albums.batchcli.failures import exit_if_no_albums, exit_with_failures
from photree.albums.batchcli.resolution import make_display_fn
from photree.albums.cmd_handler.init import batch_init
from photree.clihelpers.progress import BatchProgressBar
from photree.common.formatting import format_dry_run


def run_batch_init(
    albums: list[Path],
    display_base: Path | None,
    *,
    dry_run: bool = False,
    cwd: Path,
) -> None:
    """Initialize the metadata of *albums*, print a summary, exit 1 on any failure."""
    exit_if_no_albums(albums, display_base)

    with BatchProgressBar(
        total=len(albums),
        description="Initializing",
        done_description="init",
    ) as progress:
        result = batch_init(
            albums,
            dry_run=dry_run,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=progress.on_end,
        )

    typer.echo(
        format_dry_run(
            (
                f"\n{result.initialized} album(s) would be initialized"
                if dry_run
                else f"\nDone. {result.initialized} album(s) initialized"
            )
            + f", {len(result.failures)} failed.",
            dry_run=dry_run,
        ),
    )
    exit_with_failures(result.failures, "init", cwd)
