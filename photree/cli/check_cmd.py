"""CLI command for ``photree check``."""

from __future__ import annotations

import typer

from ..album import output as album_output
from ..album import preflight as album_preflight


def check_cmd() -> None:
    """Check that all system prerequisites are met."""
    sips_available = album_preflight.check_sips_available()
    typer.echo(album_output.sips_check(sips_available))
    if not sips_available:
        typer.echo("")
        typer.echo(album_output.sips_troubleshoot(), err=True)
        raise typer.Exit(code=1)
