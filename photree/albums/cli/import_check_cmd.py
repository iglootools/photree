"""The ``photree albums import-check`` command."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from photree.album.cli.import_preflight import run_import_preflight
from photree.album.importer.album_import import task_has_content
from photree.album.importer.tasks import discover_import_tasks
from photree.albums.cli.app import app
from photree.albums.cmd_handler.importer import scan_albums
from photree.clihelpers.console import err_console
from photree.clihelpers.options import CONFIG_OPTION
from photree.clihelpers.paths import expand_user_path, expand_user_paths
from photree.clihelpers.progress import BatchProgressBar
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import mutually_exclusive_error
from photree.common.formatting import indent
from photree.common.fs import display_path


class NotReadyReason(StrEnum):
    """Why an album cannot be imported yet."""

    NO_STAGING = "no-staging"
    EMPTY_STAGING = "empty-staging"


def _format_not_ready_reason(reason: NotReadyReason) -> str:
    match reason:
        case NotReadyReason.NO_STAGING:
            return "no to-import-* staging entries"
        case NotReadyReason.EMPTY_STAGING:
            return "to-import-* staging entries are empty"


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
    album_dir: Path,
    progress: BatchProgressBar,
) -> tuple[Path, NotReadyReason | None]:
    progress.on_start(album_dir.name)
    reason = _not_ready_reason(album_dir)
    progress.on_end(
        album_dir.name,
        success=reason is None,
        error_labels=(_format_not_ready_reason(reason),) if reason is not None else (),
    )
    return album_dir, reason


def _report_not_ready(not_ready: list[tuple[Path, NotReadyReason]], cwd: Path) -> None:
    err_console.print(
        "\n".join(
            [
                "\nNot ready:",
                *(
                    indent(
                        f"{display_path(album, cwd)}\n"
                        f"{indent(_format_not_ready_reason(reason))}",
                    )
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
                        f'"{display_path(album, cwd)}"',
                    )
                    for album, _ in not_ready
                ),
            ],
        ),
        markup=False,
    )


def _resolve_candidates(
    scan_dir: Path,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], int]:
    """
    Return the albums to check, and how many scanned directories were skipped.

    Named albums are all checked. A scan keeps what ``albums import --dir``
    would consider: the import skips a subdirectory without any
    ``to-import-*`` entry (a hidden directory, a non-album, an album with
    nothing staged), so the check leaves it out rather than failing on it.
    One whose entries are empty stays in, as the import warns about it.
    """
    match album_dirs:
        case list():
            return album_dirs, 0
        case None:
            scan = scan_albums(scan_dir)
            return (
                sorted([*scan.empty_selection, *scan.to_import]),
                len(scan.no_selection),
            )


@app.command("import-check")
def import_check_cmd(
    ctx: typer.Context,
    albums_dir: Annotated[
        Path | None,
        typer.Option(
            "--dir",
            "-d",
            help="Parent directory containing album subdirectories.",
            file_okay=False,
            callback=expand_user_path(exists=True),
        ),
    ] = None,
    album_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory (repeatable).",
            file_okay=False,
            callback=expand_user_paths(exists=True),
        ),
    ] = None,
    source: Annotated[
        Path | None,
        typer.Option(
            "--source",
            "-s",
            help="Image Capture output directory. Overrides config and default.",
            file_okay=False,
            callback=expand_user_path(),
        ),
    ] = None,
    config: CONFIG_OPTION = None,
) -> None:
    """
    Check system prerequisites and import tasks for batch import.

    Runs shared preflight checks (sips, Image Capture directory) once, then
    checks each album for non-empty to-import-{ios,std}-<name> staging entries.
    With --dir, a subdirectory without any staging entry is skipped, as
    albums import skips it.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    if albums_dir is not None and album_dirs is not None:
        raise mutually_exclusive_error(
            ("--dir", "--album-dir"),
            command="albums import-check",
        )

    # Shared preflight (sips + IC directory, no per-album selection check)
    run_import_preflight(source, config, runtime=runtime)

    albums, skipped = _resolve_candidates(
        albums_dir if albums_dir is not None else cwd,
        album_dirs,
    )
    if skipped:
        typer.echo(
            f"\nSkipped {skipped} directory(ies) without a to-import-* staging entry.",
        )
    if not albums:
        typer.echo("\nNo album directories with a to-import-* staging entry found.")
        raise typer.Exit(code=0)

    typer.echo(f"\nImport Tasks ({len(albums)} album(s)):")
    with BatchProgressBar(
        total=len(albums),
        description="Checking",
        done_description="check",
    ) as progress:
        results = [_check_album(album_dir, progress) for album_dir in albums]

    _summarize(len(albums), results, cwd)


def _summarize(
    total: int,
    results: list[tuple[Path, NotReadyReason | None]],
    cwd: Path,
) -> None:
    """Print the ready/not-ready counts; exit 1 with reasons if any is not ready."""
    not_ready = [(album, reason) for album, reason in results if reason is not None]
    typer.echo(
        f"\n{total - len(not_ready)} album(s) ready to import, "
        f"{len(not_ready)} not ready.",
    )
    if not_ready:
        _report_not_ready(not_ready, cwd)
        raise typer.Exit(code=1)
