"""CLI command for ``photree check``."""

from __future__ import annotations

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.sysdeps import format_missing_troubleshoot, format_statuses
from ...common.sysdeps import (
    SystemDependency,
    check_system_dependencies,
    missing_dependencies,
)
from . import check_app


@check_app.command("system")
def check_system_cmd() -> None:
    """Check that all system prerequisites are met."""
    statuses = check_system_dependencies(tuple(SystemDependency))
    console.print(format_statuses(statuses))

    missing = missing_dependencies(statuses)
    if missing:
        typer.echo("")
        err_console.print(format_missing_troubleshoot(missing))
        raise typer.Exit(code=1)
