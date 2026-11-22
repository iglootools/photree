"""The Rich consoles every command prints to: stdout and stderr."""

from rich.console import Console

console = Console(highlight=False, soft_wrap=True)
err_console = Console(stderr=True, highlight=False, soft_wrap=True)
