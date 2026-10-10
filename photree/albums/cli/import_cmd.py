"""``photree albums import`` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from ...album.cli.helpers import _run_preflight_checks
from ...album.faces.detect import memoized_face_analyzer_factory
from ...album.importer import batch
from ...album.importer import output as importer_output
from ...album.importer.album_import import TaskIssue
from ...album.jpeg import convert_single_file, noop_convert_single
from ...clihelpers.console import err_console
from ...clihelpers.progress import BatchProgressBar
from ...common.formatting import indent
from ...common.fs import display_path
from ...fsprotocol import LinkMode
from . import albums_app


def _count_candidates(albums_dir: Path | None, album_dirs: list[Path] | None) -> int:
    """How many albums the batch will look at (progress-bar total)."""
    match (album_dirs, albums_dir):
        case (list(), _):
            return len(album_dirs)
        case (None, Path()):
            return sum(1 for p in albums_dir.iterdir() if p.is_dir())
        case _:
            return 0


def _run_import(
    albums_dir: Path | None,
    album_dirs: list[Path] | None,
    ic_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    skip_heic_to_jpeg: bool,
) -> batch.BatchResult:
    """Run the batch import behind a progress bar.

    ``result.validation_failures`` is non-empty when validation refused the
    batch, in which case nothing was imported.
    """
    with BatchProgressBar(
        total=_count_candidates(albums_dir, album_dirs),
        description="Importing",
        done_description="import",
    ) as progress:

        def on_validation_error(name: str, errors: list[TaskIssue]) -> None:
            progress.stop()
            err_console.print(importer_output.validation_errors(name, errors))

        result = batch.run_batch_import(
            albums_dir=albums_dir,
            album_dirs=album_dirs,
            image_capture_dir=ic_dir,
            link_mode=link_mode,
            dry_run=dry_run,
            on_importing=progress.on_start,
            on_imported=lambda name: progress.on_end(name, success=True),
            on_skipped=progress.on_skipped,
            on_error=lambda name, error: progress.on_end(
                name, success=False, error_labels=(error,)
            ),
            on_validation_error=on_validation_error,
            convert_file=noop_convert_single
            if skip_heic_to_jpeg
            else convert_single_file,
            max_workers=os.cpu_count(),
            analyzer_factory=memoized_face_analyzer_factory(),
        )
    return result


def _report_failures(result: batch.BatchResult, base: Path, cwd: Path) -> None:
    err_console.print(importer_output.batch_failures(result.failed, base))
    err_console.print(
        "\n".join(
            [
                "\nTo investigate failures:",
                *(
                    indent(
                        "photree album import --album-dir "
                        f'"{display_path(album_dir, cwd)}"'
                    )
                    for album_dir, _ in result.failed
                ),
            ]
        ),
        markup=False,
    )


@albums_app.command("import")
def import_cmd(
    albums_dir: Annotated[
        Path | None,
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
        list[Path] | None,
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
        Path | None,
        typer.Option(
            "--source",
            "-s",
            help="Image Capture output directory. Overrides config and default.",
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    config: Annotated[
        str | None,
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
    """Batch import staged media for multiple albums.

    Either scan immediate subdirectories of --dir for a non-empty
    to-import-{ios,std}-<name> staging entry, or provide explicit album
    directories via --album-dir (repeatable). The two options are mutually
    exclusive. Albums without any staging entry (or with only empty ones)
    are skipped.
    """
    if albums_dir is not None and album_dirs is not None:
        err_console.print(
            "--dir and --album-dir are mutually exclusive.\n"
            "Run 'photree albums import --help' for usage."
        )
        raise typer.Exit(code=1)

    ic_dir = _run_preflight_checks(
        source, config, force=force, skip_heic_to_jpeg=skip_heic_to_jpeg
    )
    typer.echo("\nImport:")

    cwd = Path.cwd()
    scan_dir = None if album_dirs is not None else (albums_dir or cwd)
    result = _run_import(
        scan_dir,
        album_dirs,
        ic_dir,
        link_mode=link_mode,
        dry_run=dry_run,
        skip_heic_to_jpeg=skip_heic_to_jpeg,
    )
    if result.validation_failures:
        err_console.print("\nAborted: validation failed. No imports were performed.")
        raise typer.Exit(code=1)

    typer.echo(
        importer_output.batch_summary(
            result.imported, result.skipped, result.failed_count
        )
    )
    if result.failed:
        _report_failures(result, scan_dir if scan_dir is not None else cwd, cwd)
        raise typer.Exit(code=1)
