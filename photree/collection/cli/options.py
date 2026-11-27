"""Typer options shared by the single-collection commands."""

from pathlib import Path
from typing import Annotated

import typer

from photree.clihelpers.paths import expand_user_path

COLLECTION_DIR_OPTION = Annotated[
    Path,
    typer.Option(
        "--collection-dir",
        "-c",
        # Backward-compatible aliases: init/show/check/metadata set took the
        # collection directory as ``--dir/-d`` before adopting the project-wide
        # ``--collection-dir/-c`` convention. Kept so existing scripts keep
        # working; ``--dir`` is otherwise reserved for batch scan bases.
        "--dir",
        "-d",
        help="Collection directory.",
        file_okay=False,
        callback=expand_user_path(exists=True),
    ),
]
