"""CLI commands for the ``photree import`` sub-app."""

from pathlib import Path
from typing import Annotated, Optional

import typer

from ..album.exif import check_exiftool_available
from ..album.naming import check_album_naming, check_exif_date_match, parse_album_name
from ..album.output.preflight import format_naming_checks
from ..album.naming import AlbumNamingResult
from ..config import ConfigError, load_config
from ..fsprotocol import (
    LinkMode,
    SELECTION_DIR,
)
from ..album.jpeg import convert_single_file, noop_convert_single
from ..importer import image_capture, image_capture_all, output
from ..importer.image_capture import (
    plan_import_from_dirs,
    validate_import_plan,
)
from ..importer.preflight import run_preflight
from .console import console, err_console
from .progress import BatchProgressBar, StageProgressBar

DEFAULT_IMAGE_CAPTURE_DIR = Path.home() / "Pictures" / "iPhone"

import_app = typer.Typer(
    name="import",
    help="Import photos from external sources.",
    no_args_is_help=True,
)


def _run_preflight_checks(
    source: Path | None,
    config_path: str | None,
    *,
    album_dir: Path | None = None,
    force: bool = False,
    skip_heic_to_jpeg: bool = False,
) -> Path:
    """Run all preflight checks and resolve the Image Capture directory.

    Prints all check lines first, then troubleshooting for failures at the end.
    """
    image_capture_dir = _resolve_image_capture_dir(source, config_path)
    result = run_preflight(
        image_capture_dir,
        album_dir=album_dir,
        force=force,
        skip_heic_to_jpeg=skip_heic_to_jpeg,
    )

    typer.echo("Preflight Checks:")
    console.print(output.format_preflight_checks(result))

    if not result.success:
        troubleshoot = output.format_preflight_troubleshoot(result)
        if troubleshoot:
            typer.echo("")
            err_console.print(troubleshoot)
        raise typer.Exit(code=1)

    return image_capture_dir


def _resolve_image_capture_dir(
    source: Path | None,
    config_path: str | None,
) -> Path:
    """Resolve the Image Capture directory: CLI flag > config > default."""
    if source is not None:
        return source

    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=2) from exc

    if cfg.importer.image_capture_dir is not None:
        return cfg.importer.image_capture_dir

    return DEFAULT_IMAGE_CAPTURE_DIR


@import_app.command("check")
def check_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help=f"Album directory (should contain a {SELECTION_DIR}/ subfolder).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
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
    """Check that system prerequisites for import commands are met."""
    _run_preflight_checks(source, config, album_dir=album_dir)


@import_app.command("image-capture")
def image_capture_cmd(
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
    album_contributor: Annotated[
        str,
        typer.Option(
            "--contributor",
            help="Target contributor within the album (default: main).",
        ),
    ] = "main",
) -> None:
    f"""Organize files imported by macOS Image Capture into an album directory.

    Reads the {SELECTION_DIR}/ inside ALBUM_DIR, matches files from the
    Image Capture source directory, and sorts them into the contributor's
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
        err_console.print(output.validation_errors(album_dir.name, errors))
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
            contributor_name=album_contributor,
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
        err_console.print(output.unprocessed_selection_files(result.unprocessed))
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


@import_app.command("image-capture-all")
def image_capture_all_cmd(
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
        err_console.print(output.validation_errors(name, errors))

    resolved_albums_dir = (
        None
        if album_dirs is not None
        else (albums_dir if albums_dir is not None else Path(".").resolve())
    )

    result = image_capture_all.run_batch_import(
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

    typer.echo(output.batch_summary(result.imported, result.skipped))
