"""``photree albums import-check`` command."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from ...album.cli.helpers import _run_preflight_checks
from ...album.importer.album_import import task_has_content
from ...album.importer.tasks import discover_import_tasks
from ...clihelpers.console import err_console
from ...clihelpers.progress import BatchProgressBar
from ...common.formatting import indent
from ...common.fs import display_path
from . import albums_app


class NotReadyReason(StrEnum):
    """Why an album cannot be imported yet (also its progress-line label)."""

    NO_STAGING = "no to-import-* staging entries"
    EMPTY_STAGING = "to-import-* staging entries are empty"


def _not_ready_reason(album_dir: Path) -> NotReadyReason | None:
    tasks = discover_import_tasks(album_dir)
    match tasks:
        case []:
            return NotReadyReason.NO_STAGING
        case _ if not any(task_has_content(t) for t in tasks):
            return NotReadyReason.EMPTY_STAGING
        case _:
            return None


def _check_album(
    album_dir: Path, progress: BatchProgressBar
) -> tuple[Path, NotReadyReason | None]:
    progress.on_start(album_dir.name)
    reason = _not_ready_reason(album_dir)
    progress.on_end(
        album_dir.name,
        success=reason is None,
        error_labels=(reason,) if reason is not None else (),
    )
    return album_dir, reason


def _report_not_ready(not_ready: list[tuple[Path, NotReadyReason]], cwd: Path) -> None:
    err_console.print(
        "\n".join(
            [
                "\nNot ready:",
                *(
                    indent(f"{display_path(album, cwd)}\n{indent(reason)}")
                    for album, reason in not_ready
                ),
                (
                    "\nAdd a to-import-ios-<name>/ (or .csv) or "
                    "to-import-std-<name>/ staging entry to each album, then "
                    "re-run, e.g.:"
                ),
                *(
                    indent(
                        f"photree album import-check --album-dir "
                        f'"{display_path(album, cwd)}"'
                    )
                    for album, _ in not_ready
                ),
            ]
        ),
        markup=False,
    )


@albums_app.command("import-check")
def import_check_cmd(
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
            help="Album directory (repeatable).",
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
) -> None:
    """Check system prerequisites and import tasks for batch import.

    Runs shared preflight checks (sips, Image Capture directory) once, then
    checks each album for non-empty to-import-{ios,std}-<name> staging entries.
    """
    if albums_dir is not None and album_dirs is not None:
        err_console.print(
            "--dir and --album-dir are mutually exclusive.\n"
            "Run 'photree albums import-check --help' for usage."
        )
        raise typer.Exit(code=1)

    # Shared preflight (sips + IC directory, no per-album selection check)
    _run_preflight_checks(source, config)

    cwd = Path.cwd()
    scan_dir = albums_dir if albums_dir is not None else cwd
    albums = (
        album_dirs
        if album_dirs is not None
        else sorted(p for p in scan_dir.iterdir() if p.is_dir())
    )
    if not albums:
        typer.echo("\nNo album directories found.")
        raise typer.Exit(code=0)

    typer.echo(f"\nImport Tasks ({len(albums)} album(s)):")
    with BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    ) as progress:
        results = [_check_album(album_dir, progress) for album_dir in albums]

    _summarize(len(albums), results, cwd)


def _summarize(
    total: int, results: list[tuple[Path, NotReadyReason | None]], cwd: Path
) -> None:
    """Print the ready/not-ready counts; exit 1 with reasons if any is not ready."""
    not_ready = [(album, reason) for album, reason in results if reason is not None]
    typer.echo(
        f"\n{total - len(not_ready)} album(s) ready to import, "
        f"{len(not_ready)} not ready."
    )
    if not_ready:
        _report_not_ready(not_ready, cwd)
        raise typer.Exit(code=1)
