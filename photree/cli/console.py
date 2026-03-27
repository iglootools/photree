"""Shared Rich console instances for CLI output."""

from rich.console import Console

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)
