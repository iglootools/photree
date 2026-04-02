"""``photree album import`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import album_app
from .helpers import _run_preflight_checks
from ..preflight import check_exiftool_available
from ..importer import image_capture, output as importer_output
from ..importer.image_capture import plan_import_from_dirs, validate_import_plan
from ..jpeg import convert_single_file, noop_convert_single
from ..naming import (
    AlbumNamingResult,
    check_album_naming,
    check_exif_date_match,
    parse_album_name,
)
from ..preflight.output import format_naming_checks
from ...clihelpers.console import console, err_console
from ...clihelpers.options import CONFIG_OPTION
from ...clihelpers.progress import StageProgressBar
from ...fs import (
    LinkMode,
    SELECTION_DIR,
)


@album_app.command("import")
def import_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help=f"Album directory (must contain a {SELECTION_DIR}/ subfolder).",
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
    album_media_source: Annotated[
        str,
        typer.Option(
            "--media-source",
            help="Target media source within the album (default: main).",
        ),
    ] = "main",
) -> None:
    f"""Organize files imported by macOS Image Capture into an album directory.

    Reads the {SELECTION_DIR}/ inside ALBUM_DIR, matches files from the
    Image Capture source directory, and sorts them into the media source's
    archival and browsable subdirectories.

    The source directory is resolved in this order:
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

    # Pre-import naming convention check (from directory name alone)
    naming_issues = check_album_naming(album_dir.name)
    if naming_issues:
        parsed = parse_album_name(album_dir.name)
        naming_result = AlbumNamingResult(
            parsed=parsed,
            issues=naming_issues,
            exif_check=None,
        )
        typer.echo("\nNaming Convention Check:")
        console.print(format_naming_checks(naming_result))
        err_console.print(
            "\nAlbum name does not follow naming conventions. "
            "Rename the album directory before importing."
        )
        raise typer.Exit(code=1)

    # Pre-validate the import plan
    selection_path = album_dir / SELECTION_DIR
    plan = plan_import_from_dirs(selection_path, image_capture_dir)

    # Show dedup warnings (informational, doesn't block import)
    if plan.dedup_warnings:
        typer.echo("\nDedup Warnings:")
        for w in plan.dedup_warnings:
            typer.echo(f"  {w}")

    errors = validate_import_plan(plan)
    if errors:
        err_console.print(importer_output.validation_errors(album_dir.name, errors))
        raise typer.Exit(code=1)

    typer.echo("\nImport:")
    converter = noop_convert_single if skip_heic_to_jpeg else convert_single_file
    progress = StageProgressBar(
        total=4,
        labels={
            "import-ic": "Importing from Image Capture",
            "refresh-main-img": "Refreshing main-img",
            "refresh-main-vid": "Refreshing main-vid",
            "refresh-main-jpg": "Refreshing main-jpg",
        },
    )
    try:
        result = image_capture.run_import(
            album_dir=album_dir,
            image_capture_dir=image_capture_dir,
            media_source_name=album_media_source,
            link_mode=link_mode,
            dry_run=dry_run,
            on_stage_start=progress.on_start,
            on_stage_end=progress.on_end,
            convert_file=converter,
        )
    except FileNotFoundError as exc:
        progress.stop()
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        progress.stop()

    if result.unprocessed:
        err_console.print(
            importer_output.unprocessed_selection_files(result.unprocessed)
        )
        raise typer.Exit(code=1)

    # Post-import EXIF timestamp check (warning only, doesn't fail the import)
    if not dry_run and check_exiftool_available():
        parsed = parse_album_name(album_dir.name)
        if parsed is not None:
            exif_check = check_exif_date_match(album_dir, parsed.date)
            if exif_check is not None and not exif_check.matches:
                naming_result = AlbumNamingResult(
                    parsed=parsed,
                    issues=(),
                    exif_check=exif_check,
                )
                typer.echo("\nPost-Import Check:")
                console.print(format_naming_checks(naming_result))
