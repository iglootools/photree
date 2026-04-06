"""CLI commands for the ``photree collections`` sub-app."""

from __future__ import annotations

import typer

collections_app = typer.Typer(
    name="collections",
    help="Batch operations on multiple collections.",
    no_args_is_help=True,
)

from . import (  # noqa: E402, F401 — imported for command registration side effects
    check_cmd,
    import_cmd,
)
