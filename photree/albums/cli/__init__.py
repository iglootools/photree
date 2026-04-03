"""CLI commands for the ``photree albums`` sub-app."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

albums_app = typer.Typer(
    name="albums",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Shared option patterns
# ---------------------------------------------------------------------------

DIR_OPTION = typer.Option(
    "--dir",
    "-d",
    help="Base directory to recursively scan for albums.",
    exists=True,
    file_okay=False,
    resolve_path=True,
)

ALBUM_DIR_OPTION = typer.Option(
    "--album-dir",
    "-a",
    help="Album directory (repeatable).",
    exists=True,
    file_okay=False,
    resolve_path=True,
)

# Type aliases for annotated option types
DirOption = Annotated[Optional[Path], DIR_OPTION]
AlbumDirOption = Annotated[Optional[list[Path]], ALBUM_DIR_OPTION]

from . import (  # noqa: E402, F401 — imported for command registration side effects
    check_cmd,
    export_cmd,
    fix_cmd,
    fix_ios_cmd,
    import_check_cmd,
    import_cmd,
    init_cmd,
    list_cmd,
    optimize_cmd,
    refresh_cmd,
    rename_from_csv_cmd,
    stats_cmd,
)
