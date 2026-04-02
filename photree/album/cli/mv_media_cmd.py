"""``photree album mv-media`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import album_app
from .. import media_ops
from ...clihelpers.console import err_console
from ...fs import display_path


@album_app.command("mv-media")
def mv_media_cmd(
    source_album: Annotated[
        Path,
        typer.Option(
            "--source-album",
            "-s",
            help="Source album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    dest_album: Annotated[
        Path,
        typer.Option(
            "--dest-album",
            "-d",
            help="Destination album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    files: Annotated[
        list[str],
        typer.Argument(
            help="Relative file paths to move (e.g. main-jpg/IMG_E3219.jpg).",
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Move media files and all their variants from one album to another.

    For each specified file, resolves all associated variants by image number
    (iOS) or filename stem (std) across the media source's directory structure
    and moves them all. Any variant file can be used to identify the media.
    """
    cwd = Path.cwd()
    try:
        result = media_ops.move_media(source_album, dest_album, files, dry_run=dry_run)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from None

    typer.echo(media_ops.media_op_summary("Moved", result.files_by_dir))
    typer.echo(
        media_ops.media_op_check_suggestions(
            [
                str(display_path(source_album, cwd)),
                str(display_path(dest_album, cwd)),
            ]
        )
    )
