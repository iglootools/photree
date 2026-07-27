"""CLI commands for ``photree gallery metadata``."""

from __future__ import annotations

import typer

gallery_metadata_app = typer.Typer(
    name="metadata",
    help="Gallery metadata management.",
    no_args_is_help=True,
)

from . import (
    set_cmd,  # noqa: F401 — imported for command registration side effects
)
