"""Shared Rich console instances for CLI output."""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from ..common.formatting import CHECK, markup_escape

console = Console(highlight=False, soft_wrap=True)
err_console = Console(stderr=True, highlight=False, soft_wrap=True)


def log_action() -> Callable[[str], None]:
    """Return a callback that prints a check-prefixed plain-text action line."""
    return lambda msg: console.print(f"{CHECK} {markup_escape(msg)}")
