"""``photree album rm-media`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import album_app
from .. import media_ops
from ...clicommons.console import err_console
from ...fs import display_path


@album_app.command("rm-media")
def rm_media_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    files: Annotated[
        list[str],
        typer.Argument(
            help="Relative file paths to remove (e.g. main-jpg/IMG_E3219.jpg).",
        ),
    ] = [],  # noqa: B006
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Remove media files and all their variants from an album.

    For each specified file, resolves all associated variants by image number
    (iOS) or filename stem (std) across the media source's directory structure
    and removes them all. Any variant file can be used to identify the media.
    """
    if not files:
        err_console.print("No files specified.")
        raise typer.Exit(code=1)

    cwd = Path.cwd()
    try:
        result = media_ops.rm_media(album_dir, files, dry_run=dry_run, log_cwd=cwd)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from None

    typer.echo(media_ops.media_op_summary("Removed", result.files_by_dir))
    typer.echo(
        media_ops.media_op_check_suggestions([str(display_path(album_dir, cwd))])
    )
