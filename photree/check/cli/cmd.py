"""CLI command for ``photree check``."""

from __future__ import annotations

import typer

from ...album import preflight as album_preflight
from ...album.preflight import output as preflight_output
from ...clicommons.console import console, err_console
from . import check_app


@check_app.command("system")
def check_system_cmd() -> None:
    """Check that all system prerequisites are met."""
    sips_available = album_preflight.check_sips_available()
    console.print(preflight_output.sips_check(sips_available))
    if not sips_available:
        typer.echo("")
        err_console.print(preflight_output.sips_troubleshoot())
        raise typer.Exit(code=1)
