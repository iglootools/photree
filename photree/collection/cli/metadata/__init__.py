"""CLI commands for ``photree collection metadata``."""

import typer

collection_metadata_app = typer.Typer(
    name="metadata",
    help="Collection metadata management.",
    no_args_is_help=True,
)

from . import (
    set_cmd,  # noqa: F401 — imported for command registration side effects
)
