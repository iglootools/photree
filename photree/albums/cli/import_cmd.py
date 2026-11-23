"""The ``photree albums import`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.cli.import_preflight import run_import_preflight
from photree.album.faces.detect import memoized_face_analyzer_factory
from photree.album.importer import batch
from photree.album.importer import output as importer_output
from photree.album.importer.album_import import TaskIssue
from photree.album.importer.batch import ImportFailureStage
from photree.album.jpeg import convert_single_file, noop_convert_single
from photree.albums.cli.app import app
from photree.clihelpers.console import err_console
from photree.clihelpers.options import DRY_RUN_OPTION, LINK_MODE_OPTION
from photree.clihelpers.progress import BatchProgressBar
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import mutually_exclusive_error
from photree.common.exif import exiftool_session
from photree.common.formatting import format_dry_run, indent
from photree.common.fs import display_path
from photree.common.sysdeps import WhichFn
from photree.foundation.gallery_metadata import (
    resolve_gallery_metadata,
    resolve_link_mode,
)
from photree.foundation.linking import LinkMode


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
    link_mode: LinkMode | None,
    dry_run: bool,
    skip_heic_to_jpeg: bool,
    which: WhichFn,
    max_workers: int | None,
) -> batch.BatchResult:
    """
    Run the batch import behind a progress bar.

    Each album gets *link_mode*, or when it is ``None``, its gallery's.

    ``result.refused`` is true when validation refused the batch, in which
    case nothing was imported.
    """
    with (
        exiftool_session(which=which) as exiftool,
        BatchProgressBar(
            total=_count_candidates(albums_dir, album_dirs),
            description="Importing",
            done_description="import",
        ) as progress,
    ):

        def on_validation_error(name: str, errors: list[TaskIssue]) -> None:
            progress.stop()
            err_console.print(importer_output.validation_errors(name, errors))

        return batch.run_batch_import(
            albums_dir=albums_dir,
            album_dirs=album_dirs,
            image_capture_dir=ic_dir,
            link_mode_for=lambda album_dir: resolve_link_mode(link_mode, album_dir),
            dry_run=dry_run,
            on_importing=progress.on_start,
            on_imported=lambda name: progress.on_end(name, success=True),
            on_skipped=progress.on_skipped,
            on_error=lambda name, error: progress.on_end(
                name,
                success=False,
                error_labels=(error,),
            ),
            on_validation_error=on_validation_error,
            convert_file=noop_convert_single
            if skip_heic_to_jpeg
            else convert_single_file,
            max_workers=max_workers,
            analyzer_factory=memoized_face_analyzer_factory(),
            exiftool=exiftool,
        )


# Ordered so the suggestions read in the order a user would run them.
_RETRY_COMMANDS: tuple[tuple[ImportFailureStage, str], ...] = (
    (ImportFailureStage.IMPORT, "photree album import --album-dir {dir}"),
    (ImportFailureStage.JPEG, "photree album refresh --refresh-jpeg --album-dir {dir}"),
    (ImportFailureStage.FACES, "photree album detect-faces --album-dir {dir}"),
    (
        ImportFailureStage.UNPROCESSED_SELECTION,
        "photree album import-check --album-dir {dir}",
    ),
)


def retry_commands(failure: batch.AlbumFailure, cwd: Path) -> list[str]:
    """
    Return the commands that retry what actually failed for *failure*.

    A partial failure happens after the staging entries were consumed, so
    suggesting ``album import`` again would only report "nothing to import".
    """
    quoted = f'"{display_path(failure.album_dir, cwd)}"'
    return [
        template.format(dir=quoted)
        for stage, template in _RETRY_COMMANDS
        if stage in failure.stages
    ]


def _report_failures(result: batch.BatchResult, base: Path, cwd: Path) -> None:
    err_console.print(importer_output.batch_failures(result.failed, base))
    err_console.print(
        "\n".join(
            [
                "\nTo retry or investigate failures:",
                *(
                    indent(command)
                    for failure in result.failed
                    for command in retry_commands(failure, cwd)
                ),
            ],
        ),
        markup=False,
    )


@app.command("import")
def import_cmd(
    ctx: typer.Context,
    *,
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
    link_mode: LINK_MODE_OPTION = None,
    dry_run: DRY_RUN_OPTION = False,
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
    """
    Batch import staged media for multiple albums.

    Either scan immediate subdirectories of --dir for a non-empty
    to-import-{ios,std}-<name> staging entry, or provide explicit album
    directories via --album-dir (repeatable). The two options are mutually
    exclusive. Albums without any staging entry (or with only empty ones)
    are skipped.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    which = runtime.which
    if albums_dir is not None and album_dirs is not None:
        raise mutually_exclusive_error(
            ("--dir", "--album-dir"),
            command="albums import",
        )

    ic_dir = run_import_preflight(
        source,
        config,
        force=force,
        skip_heic_to_jpeg=skip_heic_to_jpeg,
        runtime=runtime,
    )
    typer.echo("\nImport:")

    scan_dir = None if album_dirs is not None else (albums_dir or cwd)
    result = _run_import(
        scan_dir,
        album_dirs,
        ic_dir,
        link_mode=link_mode,
        dry_run=dry_run,
        skip_heic_to_jpeg=skip_heic_to_jpeg,
        which=which,
        max_workers=runtime.cpu_count(),
    )
    if not result.naming_check.success:
        err_console.print(
            "\nName check:\n"
            + importer_output.naming_check_errors(result.naming_check, cwd),
        )
    if result.refused:
        err_console.print("\nAborted: validation failed. No imports were performed.")
        raise typer.Exit(code=1)

    typer.echo(
        format_dry_run(
            importer_output.batch_summary(
                result.imported,
                result.skipped,
                result.failed_count,
                dry_run=dry_run,
            ),
            dry_run=dry_run,
        ),
    )
    if not dry_run:
        _print_gallery_refresh_hint(result.scan.to_import)
    if result.failed:
        _report_failures(result, scan_dir if scan_dir is not None else cwd, cwd)
        raise typer.Exit(code=1)


def _print_gallery_refresh_hint(imported: tuple[Path, ...]) -> None:
    """Point at the gallery-level state an album import does not update."""
    if any(resolve_gallery_metadata(a) is not None for a in imported):
        typer.echo(
            "\nSome albums are in a gallery: run 'photree gallery refresh' to update "
            "face clusters and the browsable/ tree.",
        )
