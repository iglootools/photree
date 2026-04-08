"""CLI commands for the ``photree album`` sub-app."""

from __future__ import annotations

import typer

album_app = typer.Typer(
    name="album",
    help="Album management commands.",
    no_args_is_help=True,
)

from . import (  # noqa: E402, F401 — imported for command registration side effects
    check_cmd,
    detect_faces_cmd,
    export_cmd,
    fix_cmd,
    fix_exif_cmd,
    fix_ios_cmd,
    import_check_cmd,
    import_cmd,
    list_media_cmd,
    init_cmd,
    mv_media_cmd,
    optimize_cmd,
    refresh_cmd,
    rm_media_cmd,
    show_cmd,
    stats_cmd,
)
