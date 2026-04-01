"""CLI commands for the ``photree albums`` sub-app.

Albums commands operate on multiple albums at once using ``--dir`` / ``--album-dir``
to specify which albums to target. They share implementation with gallery commands
but don't require a gallery context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ..album.exporter import export_batch, output as export_output
from ..album.importer import image_capture_batch, output as importer_output
from ..album.jpeg import convert_single_file, noop_convert_single
from ..fs import (
    LinkMode,
    SELECTION_DIR,
    display_path,
)
from ..album.exporter.settings import (
    ExportSettingsError,
    resolve_export_settings,
    validate_export_settings,
)
from ..album.ios_fixes import FixIosValidationError, validate_fix_flags
from ..config import ConfigError
from .album_cmd import _check_sips_or_exit, _run_preflight_checks
from .options import (
    ALBUM_LAYOUT_OPTION,
    CHECK_BEFORE_OPTION,
    CHECK_DATE_PART_COLLISION_OPTION,
    CHECK_EXIF_DATE_MATCH_OPTION,
    CHECK_NAMING_OPTION,
    CHECKSUM_OPTION,
    CONFIG_OPTION,
    DRY_RUN_OPTION,
    EXPORT_LINK_MODE_OPTION,
    FATAL_EXIF_DATE_MATCH_OPTION,
    FATAL_SIDECAR_OPTION,
    FATAL_WARNINGS_OPTION,
    LINK_MODE_REQUIRED_OPTION,
    MV_MISCATEGORIZED_OPTION,
    PREFER_HIGHER_QUALITY_OPTION,
    PROFILE_OPTION,
    REFRESH_COMBINED_OPTION,
    REFRESH_JPEG_OPTION,
    RM_MISCATEGORIZED_OPTION,
    RM_MISCATEGORIZED_SAFE_OPTION,
    RM_ORPHAN_OPTION,
    RM_ORPHAN_SIDECAR_OPTION,
    RM_UPSTREAM_OPTION,
    SHARE_DIR_OPTION,
    SHARE_LAYOUT_OPTION,
)
from .batch_ops import (
    run_batch_check,
    run_batch_fix,
    run_batch_fix_ios,
    run_batch_init,
    run_batch_list_albums,
    run_batch_optimize,
    run_batch_stats,
)
from .gallery_cmd import (
    _resolve_batch_albums,
    _resolve_check_batch_albums,
    _resolve_init_batch_albums,
)

albums_app = typer.Typer(
    name="albums",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Shared option patterns
# ---------------------------------------------------------------------------

_DIR_OPTION = typer.Option(
    "--dir",
    "-d",
    help="Base directory to recursively scan for albums.",
    exists=True,
    file_okay=False,
    resolve_path=True,
)

_ALBUM_DIR_OPTION = typer.Option(
    "--album-dir",
    "-a",
    help="Album directory (repeatable).",
    exists=True,
    file_okay=False,
    resolve_path=True,
)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@albums_app.command("init")
def init_cmd(
    base_dir: Annotated[Optional[Path], _DIR_OPTION] = None,
    album_dirs: Annotated[Optional[list[Path]], _ALBUM_DIR_OPTION] = None,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Initialize album metadata (.photree/album.yaml) for multiple albums."""
    albums, display_base = _resolve_init_batch_albums(base_dir, album_dirs)
    run_batch_init(albums, display_base, dry_run=dry_run)


@albums_app.command("list")
def list_cmd(
    base_dir: Annotated[Optional[Path], _DIR_OPTION] = None,
    album_dirs: Annotated[Optional[list[Path]], _ALBUM_DIR_OPTION] = None,
    metadata: Annotated[
        bool,
        typer.Option(
            "--metadata/--no-metadata",
            help="Show parsed album metadata and media sources (default: enabled).",
        ),
    ] = True,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: text (default) or csv.",
        ),
    ] = "text",
    output_file: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Write output to a file instead of stdout.",
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """List all discovered albums with their metadata and media sources."""
    albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_list_albums(
        albums,
        display_base,
        metadata=metadata,
        output_format=output_format,
        output_file=output_file,
    )


@albums_app.command("check")
def check_cmd(
    base_dir: Annotated[Optional[Path], _DIR_OPTION] = None,
    album_dirs: Annotated[Optional[list[Path]], _ALBUM_DIR_OPTION] = None,
    checksum: CHECKSUM_OPTION = True,
    fatal_warnings: FATAL_WARNINGS_OPTION = False,
    fatal_sidecar_arg: FATAL_SIDECAR_OPTION = False,
    fatal_exif_date_match: FATAL_EXIF_DATE_MATCH_OPTION = True,
    check_naming: CHECK_NAMING_OPTION = True,
    check_date_part_collision: CHECK_DATE_PART_COLLISION_OPTION = True,
    check_exif_date_match: CHECK_EXIF_DATE_MATCH_OPTION = True,
) -> None:
    """Check all albums under a directory or from an explicit list."""
    albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_check(
        albums,
        display_base,
        checksum=checksum,
        fatal_warnings=fatal_warnings,
        fatal_sidecar_arg=fatal_sidecar_arg,
        fatal_exif_date_match=fatal_exif_date_match,
        check_naming=check_naming,
        check_date_part_collision=check_date_part_collision,
        check_exif_date_match=check_exif_date_match,
    )


@albums_app.command("fix")
def fix_cmd(
    base_dir: Annotated[Optional[Path], _DIR_OPTION] = None,
    album_dirs: Annotated[Optional[list[Path]], _ALBUM_DIR_OPTION] = None,
    fix_id: Annotated[
        bool,
        typer.Option("--id", help="Generate missing album IDs (.photree/album.yaml)."),
    ] = False,
    new_id: Annotated[
        bool,
        typer.Option("--new-id", help="Regenerate album IDs (replaces existing IDs)."),
    ] = False,
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix all albums under a directory or from an explicit list."""
    if not fix_id and not new_id and not refresh_jpeg:
        typer.echo(
            "No fix specified. Run photree albums fix --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)

    if refresh_jpeg:
        _check_sips_or_exit()

    albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        refresh_jpeg=refresh_jpeg,
        dry_run=dry_run,
    )


@albums_app.command("fix-ios")
def fix_ios_cmd(
    base_dir: Annotated[Optional[Path], _DIR_OPTION] = None,
    album_dirs: Annotated[Optional[list[Path]], _ALBUM_DIR_OPTION] = None,
    link_mode: LINK_MODE_REQUIRED_OPTION = LinkMode.HARDLINK,
    refresh_combined: REFRESH_COMBINED_OPTION = False,
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    prefer_higher_quality_when_dups: PREFER_HIGHER_QUALITY_OPTION = False,
    rm_orphan_sidecar: RM_ORPHAN_SIDECAR_OPTION = False,
    rm_miscategorized: RM_MISCATEGORIZED_OPTION = False,
    rm_miscategorized_safe: RM_MISCATEGORIZED_SAFE_OPTION = False,
    mv_miscategorized: MV_MISCATEGORIZED_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Apply fix-ios to all iOS albums under a directory or from an explicit list."""
    try:
        validate_fix_flags(
            refresh_combined=refresh_combined,
            refresh_jpeg=refresh_jpeg,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
            rm_orphan_sidecar=rm_orphan_sidecar,
            prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
            rm_miscategorized=rm_miscategorized,
            rm_miscategorized_safe=rm_miscategorized_safe,
            mv_miscategorized=mv_miscategorized,
        )
    except FixIosValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    albums, display_base = _resolve_batch_albums(base_dir, album_dirs)
    run_batch_fix_ios(
        albums,
        display_base,
        link_mode=link_mode,
        dry_run=dry_run,
        refresh_combined=refresh_combined,
        refresh_jpeg=refresh_jpeg,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
    )


@albums_app.command("optimize")
def optimize_cmd(
    base_dir: Annotated[Optional[Path], _DIR_OPTION] = None,
    album_dirs: Annotated[Optional[list[Path]], _ALBUM_DIR_OPTION] = None,
    link_mode: LINK_MODE_REQUIRED_OPTION = LinkMode.HARDLINK,
    check: CHECK_BEFORE_OPTION = True,
    checksum: CHECKSUM_OPTION = True,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Optimize all iOS albums under a directory or from an explicit list."""
    albums, display_base = _resolve_batch_albums(base_dir, album_dirs)
    run_batch_optimize(
        albums,
        display_base,
        link_mode=link_mode,
        check=check,
        checksum=checksum,
        dry_run=dry_run,
    )


@albums_app.command("stats")
def stats_cmd(
    base_dir: Annotated[Optional[Path], _DIR_OPTION] = None,
    album_dirs: Annotated[Optional[list[Path]], _ALBUM_DIR_OPTION] = None,
) -> None:
    """Show aggregated disk usage and content statistics for all albums."""
    albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_stats(albums, display_base)


# ---------------------------------------------------------------------------
# Image Capture batch import check / import
# ---------------------------------------------------------------------------


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

    from .progress import BatchProgressBar

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

    from .console import err_console
    from .progress import BatchProgressBar

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

    result = image_capture_batch.run_batch_import(
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


# ---------------------------------------------------------------------------
# Export batch command
# ---------------------------------------------------------------------------


@albums_app.command("export")
def export_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to scan for albums.",
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
            help="Album directory to export (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    share_dir: SHARE_DIR_OPTION = None,
    profile: PROFILE_OPTION = None,
    config: CONFIG_OPTION = None,
    share_layout: SHARE_LAYOUT_OPTION = None,
    album_layout: ALBUM_LAYOUT_OPTION = None,
    link_mode: EXPORT_LINK_MODE_OPTION = None,
) -> None:
    """Batch export multiple albums to a shared directory.

    Either scan --dir for albums or provide explicit album directories via
    --album-dir (repeatable). The two options are mutually exclusive.
    """
    from .progress import BatchProgressBar

    cwd = Path.cwd()

    if base_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    try:
        settings = resolve_export_settings(
            profile_name=profile,
            share_dir=share_dir,
            share_layout=share_layout,
            album_layout=album_layout,
            link_mode=link_mode,
            config_path=config,
        )
        validate_export_settings(settings)
    except (ExportSettingsError, ConfigError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    resolved_base = (
        None
        if album_dirs is not None
        else (base_dir if base_dir is not None else Path(".").resolve())
    )

    # Determine album count for progress bar
    albums = (
        list(album_dirs)
        if album_dirs is not None
        else export_batch.discover_albums(resolved_base)  # type: ignore[arg-type]
    )

    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    progress = BatchProgressBar(
        total=len(albums), description="Exporting", done_description="export"
    )

    result = export_batch.run_batch_export(
        base_dir=resolved_base,
        album_dirs=album_dirs,
        share_dir=settings.share_dir,
        share_layout=settings.share_layout,
        album_layout=settings.album_layout,
        link_mode=settings.link_mode,
        on_exporting=progress.on_start,
        on_exported=lambda name: progress.on_end(name, success=True),
        on_error=lambda name, error: progress.on_end(name, success=False),
    )
    progress.stop()

    typer.echo(export_output.batch_export_summary(result.exported, len(result.failed)))

    if result.failed:
        typer.echo("\nFailed albums:", err=True)
        for album_dir_path, error in result.failed:
            typer.echo(f"  {display_path(album_dir_path, cwd)}: {error}", err=True)
        raise typer.Exit(code=1)
