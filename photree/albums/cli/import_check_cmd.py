"""``photree albums import-check`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import albums_app
from ...fs import SELECTION_DIR
from ...album.cli.helpers import _run_preflight_checks
from ...clicommons.progress import BatchProgressBar


@albums_app.command("import-check")
def import_check_cmd(
    albums_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Parent directory containing album subdirectories.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    album_dirs: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    source: Annotated[
        Optional[Path],
        typer.Option(
            "--source",
            "-s",
            help="Image Capture output directory. Overrides config and default.",
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    config: Annotated[
        Optional[str],
        typer.Option(
            "--config",
            "-c",
            help="Path to config file.",
        ),
    ] = None,
) -> None:
    f"""Check system prerequisites and selection directories for batch import.

    Runs shared preflight checks (sips, Image Capture directory) once, then
    checks each album's {SELECTION_DIR}/ status.
    """
    if albums_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    # Shared preflight (sips + IC directory, no per-album selection check)
    _run_preflight_checks(source, config)

    # Resolve album list
    if album_dirs is not None:
        albums = album_dirs
    else:
        scan_dir = albums_dir if albums_dir is not None else Path(".").resolve()
        albums = sorted(p for p in scan_dir.iterdir() if p.is_dir())

    if not albums:
        typer.echo("\nNo album directories found.")
        raise typer.Exit(code=0)

    typer.echo(f"\nSelection Directories ({len(albums)} album(s)):")
    progress = BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    )

    ready = 0
    not_ready: list[tuple[Path, str]] = []
    for album_dir in albums:
        album_name = album_dir.name
        progress.on_start(album_name)
        selection_path = album_dir / SELECTION_DIR
        if not selection_path.is_dir():
            progress.on_end(album_name, success=False, error_labels=("no to-import/",))
            not_ready.append((album_dir, "not found"))
        elif not any(selection_path.iterdir()):
            progress.on_end(album_name, success=False, error_labels=("empty",))
            not_ready.append((album_dir, "empty"))
        else:
            progress.on_end(album_name, success=True)
            ready += 1
    progress.stop()

    typer.echo(f"\n{ready} album(s) ready to import, {len(not_ready)} not ready.")
    if not_ready:
        raise typer.Exit(code=1)
