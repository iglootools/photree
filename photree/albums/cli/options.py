"""The ``--dir`` and ``--album-dir`` options that select a batch's albums."""

from pathlib import Path
from typing import Annotated

import typer

from photree.clihelpers.paths import expand_user_path, expand_user_paths

DIR_OPTION = Annotated[
    Path | None,
    typer.Option(
        "--dir",
        "-d",
        help="Base directory to recursively scan for albums.",
        file_okay=False,
        callback=expand_user_path(exists=True),
    ),
]

ALBUM_DIR_OPTION = Annotated[
    list[Path] | None,
    typer.Option(
        "--album-dir",
        "-a",
        help="Album directory (repeatable).",
        file_okay=False,
        callback=expand_user_paths(exists=True),
    ),
]
