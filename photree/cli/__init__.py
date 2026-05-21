"""Typer CLI for photree."""

from .app import app

__all__ = ["app", "main"]


def main() -> None:
    """Main CLI entry point."""
    app()
