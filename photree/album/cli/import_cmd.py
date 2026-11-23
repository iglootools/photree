"""The ``photree album import`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.check.exif_date import AlbumNamingResult, check_exif_date_match
from photree.album.check.output.album import format_naming_checks
from photree.album.cli.app import app
from photree.album.cli.import_preflight import run_import_preflight
from photree.album.cli.media_source_conflict import exit_on_media_source_conflict
from photree.album.cli.runtime import RunImportFn, album_runtime_of
from photree.album.faces.detect import memoized_face_analyzer_factory
from photree.album.importer import output as importer_output
from photree.album.importer.album_import import (
    AlbumImportResult,
    EmptyImageCaptureDirError,
    NoImportTasksError,
    import_stage_labels,
    validate_album_import,
)
from photree.album.importer.collision import ArchiveCollision, ImportCollisionError
from photree.album.importer.naming_gate import check_import_naming
from photree.album.importer.tasks import discover_import_tasks
from photree.album.jpeg import convert_single_file, noop_convert_single
from photree.album.naming import parse_album_name
from photree.clihelpers.console import console, err_console
from photree.clihelpers.options import CONFIG_OPTION, DRY_RUN_OPTION, LINK_MODE_OPTION
from photree.clihelpers.progress import StageProgressBar
from photree.common.exif import ExifTagReader, exiftool_session
from photree.common.formatting import format_dry_run
from photree.common.fs import display_path, list_files
from photree.common.sysdeps import WhichFn
from photree.foundation.gallery_metadata import (
    resolve_gallery_metadata,
    resolve_link_mode,
)
from photree.foundation.linking import LinkMode


@app.command("import")
def import_cmd(
    ctx: typer.Context,
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory (with to-import-{ios,std}-<name> staging dirs).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path(),
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
    config: CONFIG_OPTION = None,
    link_mode: LINK_MODE_OPTION = None,
    *,
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
    Import an album's staged media into its media sources.

    Discovers all ``to-import-{ios,std}-<name>`` staging entries in ALBUM_DIR
    and imports each into its target media source:

    - ``to-import-ios-<name>/`` (and/or ``to-import-ios-<name>.csv``) is a
      selection list matched by image number against the Image Capture source.
    - ``to-import-std-<name>/`` holds ``orig/`` and ``edit/`` files that are
      imported directly (no Image Capture source needed).

    The Image Capture source directory is resolved in this order:
    1. --source flag (explicit)
    2. image-capture-dir from config file
    3. Default: ~/Pictures/iPhone
    """
    runtime = album_runtime_of(ctx)
    cwd = runtime.cwd()
    which = runtime.which
    image_capture_dir = run_import_preflight(
        source,
        config,
        album_dir=album_dir,
        force=force,
        skip_heic_to_jpeg=skip_heic_to_jpeg,
        runtime=runtime,
    )
    album_display = display_path(album_dir, cwd)

    _require_valid_name(album_dir, album_display, cwd=cwd)
    _require_valid_tasks(album_dir, image_capture_dir, album_display)

    typer.echo(format_dry_run("\nImport:", dry_run=dry_run))
    with (
        exiftool_session(which=which) as exiftool,
        exit_on_media_source_conflict(cwd),
    ):
        result = _run_import(
            album_dir,
            image_capture_dir,
            link_mode=resolve_link_mode(link_mode, album_dir),
            dry_run=dry_run,
            skip_heic_to_jpeg=skip_heic_to_jpeg,
            exiftool=exiftool,
            max_workers=runtime.cpu_count(),
            cwd=cwd,
            run_import=runtime.run_import,
        )

    problems = importer_output.import_problems(result, str(album_display))
    if problems is not None:
        err_console.print(problems)
        raise typer.Exit(code=1)

    if not dry_run:
        _post_import_exif_check(album_dir, which=which)
        _print_gallery_refresh_hint(album_dir)


def _require_valid_name(
    album_dir: Path,
    album_display: Path,
    *,
    cwd: Path,
) -> None:
    """
    Pre-import light check: naming convention and date collisions.

    The same check gates ``gallery import``; running it here surfaces a
    problem while the album is being filled rather than when it reaches the
    gallery.
    """
    check = check_import_naming([album_dir])
    if check.success:
        return
    typer.echo("\nName Check:")
    console.print(importer_output.naming_check_errors(check, cwd))
    err_console.print(
        f"\nAlbum name does not follow naming conventions or collides with "
        f"another album's date. Rename {album_display} as shown above, then run "
        "'photree album import --album-dir \"<renamed-album-dir>\"'.",
        markup=False,
    )
    raise typer.Exit(code=1)


def _require_valid_tasks(
    album_dir: Path,
    image_capture_dir: Path,
    album_display: Path,
) -> None:
    """Pre-validate every staging entry before importing any of them."""
    if not discover_import_tasks(album_dir):
        err_console.print(
            f"No to-import-{{ios,std}}-<media-source> "
            f"staging entries in {album_display}.",
            markup=False,
        )
        err_console.print(
            "Create one (e.g. a to-import-ios-main/ selection), then run "
            f"'photree album import --album-dir \"{album_display}\"'.",
            markup=False,
        )
        raise typer.Exit(code=1)

    validation = validate_album_import(album_dir, list_files(image_capture_dir))
    # Dedup warnings and warnings are informational and do not block import.
    warnings = importer_output.validation_warnings(validation)
    if warnings is not None:
        console.print("\n" + warnings)
    if validation.errors:
        err_console.print(
            importer_output.validation_errors(album_dir.name, list(validation.errors)),
        )
        raise typer.Exit(code=1)


def _run_import(
    album_dir: Path,
    image_capture_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    skip_heic_to_jpeg: bool,
    exiftool: ExifTagReader | None,
    max_workers: int | None,
    cwd: Path,
    run_import: RunImportFn,
) -> AlbumImportResult:
    labels = import_stage_labels(discover_import_tasks(album_dir))
    with StageProgressBar(total=len(labels), labels=labels) as progress:
        try:
            return run_import(
                album_dir=album_dir,
                image_capture_dir=image_capture_dir,
                link_mode=link_mode,
                dry_run=dry_run,
                on_stage_start=progress.on_start,
                on_stage_end=progress.on_end,
                convert_file=(
                    noop_convert_single if skip_heic_to_jpeg else convert_single_file
                ),
                max_workers=max_workers,
                exiftool=exiftool,
                analyzer_factory=memoized_face_analyzer_factory(),
            )
        # The pre-validation above makes these unlikely, but run_import
        # re-checks them itself (the Image Capture directory may have emptied,
        # or the archive changed, in between): report, never a traceback.
        except (NoImportTasksError, EmptyImageCaptureDirError) as exc:
            err_console.print(importer_output.import_error(exc, cwd))
            raise typer.Exit(code=1) from exc
        except ImportCollisionError as exc:
            err_console.print(
                importer_output.format_archive_collision(
                    ArchiveCollision(exc.media_source, exc.keys),
                ),
                markup=False,
            )
            raise typer.Exit(code=1) from exc


def _post_import_exif_check(album_dir: Path, *, which: WhichFn) -> None:
    """Warn (without failing the import) when EXIF dates disagree with the name."""
    parsed = parse_album_name(album_dir.name)
    if parsed is None:
        return
    with exiftool_session(which=which) as exiftool:
        if exiftool is None:
            return
        exif_check = check_exif_date_match(album_dir, parsed.date, exiftool=exiftool)
    if exif_check is not None and not exif_check.matches:
        typer.echo("\nPost-Import Check:")
        console.print(
            format_naming_checks(
                AlbumNamingResult(parsed=parsed, issues=(), exif_check=exif_check),
            ),
        )


def _print_gallery_refresh_hint(album_dir: Path) -> None:
    """Point at the gallery-level state an album import does not update."""
    if resolve_gallery_metadata(album_dir) is not None:
        typer.echo(
            "\nThis album is in a gallery: run 'photree gallery refresh' to update "
            "face clusters and the browsable/ tree.",
        )
