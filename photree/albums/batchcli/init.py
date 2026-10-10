"""``albums init`` / batch init wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ...clihelpers.progress import BatchProgressBar
from ..cmd_handler.init import batch_init
from .failures import exit_if_no_albums, exit_with_failures
from .resolution import make_display_fn


def run_batch_init(
    albums: list[Path],
    display_base: Path | None,
    *,
    dry_run: bool = False,
) -> None:
    """Shared implementation for albums init."""
    cwd = Path.cwd()
    exit_if_no_albums(albums, display_base)

    with BatchProgressBar(
        total=len(albums), description="Initializing", done_description="init"
    ) as progress:
        result = batch_init(
            albums,
            dry_run=dry_run,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    typer.echo(
        f"\nDone. {result.initialized} album(s) initialized, "
        f"{len(result.failures)} failed."
    )
    exit_with_failures(result.failures, "init", cwd)
