"""``photree album import`` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.options import CONFIG_OPTION
from ...clihelpers.progress import StageProgressBar
from ...common.exif import exiftool_session
from ...common.fs import display_path, list_files
from ...fsprotocol import LinkMode
from ..check.output import derived_failures_report, format_naming_checks
from ..faces.detect import memoized_face_analyzer_factory
from ..importer import album_import
from ..importer import output as importer_output
from ..importer.album_import import (
    AlbumImportResult,
    EmptyImageCaptureDirError,
    NoImportTasksError,
    import_stage_labels,
    validate_album_import,
)
from ..importer.collision import ArchiveCollision, ImportCollisionError
from ..importer.tasks import discover_import_tasks
from ..jpeg import convert_single_file, noop_convert_single
from ..naming import (
    AlbumNamingResult,
    check_album_naming,
    check_exif_date_match,
    parse_album_name,
)
from . import album_app
from .helpers import _run_preflight_checks, exit_on_media_source_conflict


@album_app.command("import")
def import_cmd(
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
    ] = Path("."),
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
    """Import an album's staged media into its media sources.

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
    image_capture_dir = _run_preflight_checks(
        source,
        config,
        album_dir=album_dir,
        force=force,
        skip_heic_to_jpeg=skip_heic_to_jpeg,
    )
    album_display = display_path(album_dir, Path.cwd())

    _require_valid_name(album_dir, album_display)
    _require_valid_tasks(album_dir, image_capture_dir, album_display)

    typer.echo("\nImport:")
    with exit_on_media_source_conflict(Path.cwd()):
        result = _run_import(
            album_dir,
            image_capture_dir,
            link_mode=link_mode,
            dry_run=dry_run,
            skip_heic_to_jpeg=skip_heic_to_jpeg,
        )

    if _report_import_problems(result, album_display):
        raise typer.Exit(code=1)

    if not dry_run:
        _post_import_exif_check(album_dir)


def _require_valid_name(album_dir: Path, album_display: Path) -> None:
    """Pre-import naming convention check (from the directory name alone)."""
    naming_issues = check_album_naming(album_dir.name)
    if not naming_issues:
        return
    typer.echo("\nNaming Convention Check:")
    console.print(
        format_naming_checks(
            AlbumNamingResult(
                parsed=parse_album_name(album_dir.name),
                issues=naming_issues,
                exif_check=None,
            )
        )
    )
    err_console.print(
        f"\nAlbum name does not follow naming conventions. Rename {album_display} "
        "to the expected form shown above, then run "
        "'photree album import --album-dir \"<renamed-album-dir>\"'."
    )
    raise typer.Exit(code=1)


def _require_valid_tasks(
    album_dir: Path, image_capture_dir: Path, album_display: Path
) -> None:
    """Pre-validate every staging entry before importing any of them."""
    if not discover_import_tasks(album_dir):
        err_console.print(
            f"No to-import-{{ios,std}}-<media-source> staging entries in {album_display}."
        )
        err_console.print(
            "Create one (e.g. a to-import-ios-main/ selection), then run "
            f"'photree album import --album-dir \"{album_display}\"'."
        )
        raise typer.Exit(code=1)

    validation = validate_album_import(album_dir, list_files(image_capture_dir))
    # Dedup warnings and warnings are informational and do not block import.
    warnings = importer_output.validation_warnings(validation)
    if warnings is not None:
        console.print("\n" + warnings)
    if validation.errors:
        err_console.print(
            importer_output.validation_errors(album_dir.name, list(validation.errors))
        )
        raise typer.Exit(code=1)


def _run_import(
    album_dir: Path,
    image_capture_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    skip_heic_to_jpeg: bool,
) -> AlbumImportResult:
    labels = import_stage_labels(discover_import_tasks(album_dir))
    with StageProgressBar(total=len(labels), labels=labels) as progress:
        try:
            return album_import.run_import(
                album_dir=album_dir,
                image_capture_dir=image_capture_dir,
                link_mode=link_mode,
                dry_run=dry_run,
                on_stage_start=progress.on_start,
                on_stage_end=progress.on_end,
                convert_file=(
                    noop_convert_single if skip_heic_to_jpeg else convert_single_file
                ),
                max_workers=os.cpu_count(),
                analyzer_factory=memoized_face_analyzer_factory(),
            )
        # The pre-validation above makes these unlikely, but run_import
        # re-checks them itself (the Image Capture directory may have emptied,
        # or the archive changed, in between): report, never a traceback.
        except (NoImportTasksError, EmptyImageCaptureDirError) as exc:
            err_console.print(importer_output.import_error(exc, Path.cwd()))
            raise typer.Exit(code=1) from exc
        except ImportCollisionError as exc:
            err_console.print(
                importer_output.format_archive_collision(
                    ArchiveCollision(exc.media_source, exc.keys)
                )
            )
            raise typer.Exit(code=1) from exc


def _report_import_problems(result: AlbumImportResult, album_display: Path) -> bool:
    """Report every problem of a finished import; return whether there was one.

    JPEG failures, face detection failures, and unprocessed selection files
    are independent: reporting only the first would hide the others until the
    next run.
    """
    if result.jpeg_failures or result.face_failures:
        err_console.print(
            "The media imported, but its derived data is incomplete:\n"
            + derived_failures_report(
                result.jpeg_failures, result.face_failures, str(album_display)
            )
        )
    if result.unprocessed:
        err_console.print(
            importer_output.unprocessed_selection_files(result.unprocessed)
        )
    return bool(result.jpeg_failures or result.face_failures or result.unprocessed)


def _post_import_exif_check(album_dir: Path) -> None:
    """Warn (without failing the import) when EXIF dates disagree with the name."""
    parsed = parse_album_name(album_dir.name)
    if parsed is None:
        return
    with exiftool_session() as exiftool:
        if exiftool is None:
            return
        exif_check = check_exif_date_match(album_dir, parsed.date, exiftool=exiftool)
    if exif_check is not None and not exif_check.matches:
        typer.echo("\nPost-Import Check:")
        console.print(
            format_naming_checks(
                AlbumNamingResult(parsed=parsed, issues=(), exif_check=exif_check)
            )
        )
