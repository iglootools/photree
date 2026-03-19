"""Typer CLI for photree."""

from .app import app

# Import command modules to register their @app.command() decorators.
from . import import_cmd as _import_cmd  # noqa: F401

__all__ = ["app", "main"]


def main() -> None:
    """Main CLI entry point."""
    app()
