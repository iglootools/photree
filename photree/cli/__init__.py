"""Typer CLI for photree."""

from .app import app

__all__ = ["app", "main"]


def main() -> None:
    """Main CLI entry point."""
    import sys

    from ..clihelpers.console import err_console
    from ..clihelpers.sysdeps import format_missing_troubleshoot
    from ..common.sysdeps import MissingSystemDependencyError

    try:
        app()
    except MissingSystemDependencyError as exc:
        # Safety net for code paths not fronted by require_system_deps: without
        # it a missing binary surfaces as an unhandled traceback.
        err_console.print(str(exc))
        err_console.print("")
        err_console.print(format_missing_troubleshoot(exc.missing))
        sys.exit(1)
