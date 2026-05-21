"""CLI commands for the ``photree collection`` sub-app."""

from __future__ import annotations

import typer

collection_app = typer.Typer(
    name="collection",
    help="Collection management commands.",
    no_args_is_help=True,
)

from .metadata import collection_metadata_app  # noqa: E402

collection_app.add_typer(collection_metadata_app)

from . import (  # noqa: E402, F401 — imported for command registration side effects
    check_cmd,
    import_cmd,
    init_cmd,
    show_cmd,
)
