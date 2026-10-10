"""Typer options shared by the single-collection commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

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
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
]
