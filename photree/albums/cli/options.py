"""The ``--dir`` and ``--album-dir`` options that select a batch's albums."""

from pathlib import Path
from typing import Annotated

import typer

DIR_OPTION = Annotated[
    Path | None,
    typer.Option(
        "--dir",
        "-d",
        help="Base directory to recursively scan for albums.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
]

ALBUM_DIR_OPTION = Annotated[
    list[Path] | None,
    typer.Option(
        "--album-dir",
        "-a",
        help="Album directory (repeatable).",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
]
