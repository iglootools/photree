"""CLI commands for the ``photree gallery`` sub-app."""

from __future__ import annotations

import typer

gallery_app = typer.Typer(
    name="gallery",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)

from . import (  # noqa: E402, F401 — imported for command registration side effects
    check_cmd,
    export_cmd,
    fix_cmd,
    fix_ios_cmd,
    import_all_cmd,
    import_cmd,
    init_cmd,
    list_albums_cmd,
    optimize_cmd,
    rename_from_csv_cmd,
    show_cmd,
    stats_cmd,
)
