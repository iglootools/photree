"""CLI for ``photree check``."""

from __future__ import annotations

import typer

check_app = typer.Typer(
    name="check",
    help="System prerequisite checks.",
    no_args_is_help=True,
)

from . import cmd  # noqa: E402, F401 — imported for command registration side effects
