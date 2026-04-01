"""Shared Rich console instances for CLI output."""

from rich.console import Console

console = Console(highlight=False, soft_wrap=True)
err_console = Console(stderr=True, highlight=False, soft_wrap=True)
