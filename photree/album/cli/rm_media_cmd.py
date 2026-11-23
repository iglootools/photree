"""The ``photree album rm-media`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album import media
from photree.album.cli.app import app
from photree.album.cli.media_op_output import (
    format_media_op_check_suggestions,
    format_media_op_error,
    format_media_op_summary,
)
from photree.album.cli.media_source_conflict import exit_on_media_source_conflict
from photree.clihelpers.console import err_console
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import no_files_error
from photree.common.formatting import format_dry_run
from photree.common.fs import display_path


@app.command("rm-media")
def rm_media_cmd(
    ctx: typer.Context,
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
    ] = Path(),
    files: Annotated[
        list[str],
        typer.Argument(
            help="Relative file paths to remove (e.g. main-jpg/IMG_E3219.jpg).",
        ),
    ] = [],  # noqa: B006
    *,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """
    Remove media files and all their variants from an album.

    For each specified file, resolves all associated variants by image number
    (iOS) or filename stem (std) across the media source's directory structure
    and removes them all. Any variant file can be used to identify the media.
    """
    if not files:
        raise no_files_error()

    cwd = runtime_of(ctx).cwd()
    with exit_on_media_source_conflict(cwd):
        try:
            result = media.rm_media(album_dir, files, dry_run=dry_run)
        except media.MediaOpError as exc:
            err_console.print(format_media_op_error(exc, cwd), markup=False)
            raise typer.Exit(code=1) from None

    typer.echo(
        format_dry_run(
            format_media_op_summary("remove", result.files_by_dir, dry_run=dry_run),
            dry_run=dry_run,
        ),
    )
    typer.echo(format_media_op_check_suggestions([str(display_path(album_dir, cwd))]))
