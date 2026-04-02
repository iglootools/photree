"""``photree albums import`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import albums_app
from ...album.importer import batch, output as importer_output
from ...album.jpeg import convert_single_file, noop_convert_single
from ...fs import LinkMode, SELECTION_DIR
from ...album.cli.helpers import _run_preflight_checks


@albums_app.command("import")
def import_cmd(
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
            help="Album directory to import (repeatable).",
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
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = LinkMode.HARDLINK,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Skip preflight checks on the source directory.",
        ),
    ] = False,
    skip_heic_to_jpeg: Annotated[
        bool,
        typer.Option(
            "--skip-heic-to-jpeg",
            help="Skip HEIC-to-JPEG conversion (and the sips availability check).",
        ),
    ] = False,
) -> None:
    f"""Batch import from Image Capture for multiple albums.

    Either scan immediate subdirectories of --dir for a non-empty
    {SELECTION_DIR}/ folder, or provide explicit album directories via
    --album-dir (repeatable). The two options are mutually exclusive.
    Albums without {SELECTION_DIR}/ (or with an empty one) are skipped.
    """
    if albums_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    from ...clihelpers.console import err_console
    from ...clihelpers.progress import BatchProgressBar

    ic_dir = _run_preflight_checks(
        source, config, force=force, skip_heic_to_jpeg=skip_heic_to_jpeg
    )

    typer.echo("\nImport:")
    converter = noop_convert_single if skip_heic_to_jpeg else convert_single_file

    if album_dirs is not None:
        progress = BatchProgressBar(
            total=len(album_dirs), description="Importing", done_description="import"
        )
    else:
        resolved_dir = albums_dir if albums_dir is not None else Path(".").resolve()
        all_subdirs = [p for p in resolved_dir.iterdir() if p.is_dir()]
        progress = BatchProgressBar(
            total=len(all_subdirs), description="Importing", done_description="import"
        )

    has_validation_errors = False

    def _on_validation_error(name: str, errors: list) -> None:
        nonlocal has_validation_errors
        has_validation_errors = True
        progress.stop()
        err_console.print(importer_output.validation_errors(name, errors))

    resolved_albums_dir = (
        None
        if album_dirs is not None
        else (albums_dir if albums_dir is not None else Path(".").resolve())
    )

    result = batch.run_batch_import(
        albums_dir=resolved_albums_dir,
        album_dirs=album_dirs,
        image_capture_dir=ic_dir,
        link_mode=link_mode,
        dry_run=dry_run,
        on_importing=progress.on_start,
        on_imported=lambda name: progress.on_end(name, success=True),
        on_skipped=progress.on_skipped,
        on_error=lambda name, error: progress.on_end(name, success=False),
        on_validation_error=_on_validation_error,
        convert_file=converter,
    )
    progress.stop()

    if has_validation_errors:
        err_console.print("\nAborted: validation failed. No imports were performed.")
        raise typer.Exit(code=1)

    typer.echo(importer_output.batch_summary(result.imported, result.skipped))
