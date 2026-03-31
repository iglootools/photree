"""CLI commands for the ``photree albums`` sub-app.

Albums commands operate on multiple albums at once using ``--dir`` / ``--album-dir``
to specify which albums to target. They share implementation with gallery commands
but don't require a gallery context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ..album.importer import image_capture_batch, output as importer_output
from ..album.jpeg import convert_single_file, noop_convert_single
from ..fsprotocol import LinkMode, SELECTION_DIR
from .album_cmd import _check_sips_or_exit, _run_preflight_checks, _validate_fix_flags
from .batch_ops import (
    run_batch_check,
    run_batch_fix,
    run_batch_fix_ios,
    run_batch_list_albums,
    run_batch_optimize,
    run_batch_stats,
)
from .gallery_cmd import (
    _resolve_batch_albums,
    _resolve_batch_albums_with,
    _resolve_check_batch_albums,
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
) -> None:
    """List all discovered albums with their metadata and media sources."""
    albums, display_base = _resolve_check_batch_albums(base_dir, album_dirs)
    run_batch_list_albums(
        albums, display_base, metadata=metadata, output_format=output_format
    )


@albums_app.command("check")
def check_cmd(
    base_dir: Annotated[Optional[Path], _DIR_OPTION] = None,
    album_dirs: Annotated[Optional[list[Path]], _ALBUM_DIR_OPTION] = None,
    checksum: Annotated[
        bool,
        typer.Option(
            "--checksum/--no-checksum",
            help="Enable/disable SHA-256 checksum verification (default: enabled).",
        ),
    ] = True,
    fatal_warnings: Annotated[
        bool,
        typer.Option(
            "--fatal-warnings",
            "-W",
            help="Treat all warnings as errors (implies --fatal-sidecar).",
        ),
    ] = False,
    fatal_sidecar_arg: Annotated[
        bool,
        typer.Option(
            "--fatal-sidecar",
            help="Treat missing-sidecar warnings as errors.",
        ),
    ] = False,
    fatal_exif_date_match: Annotated[
        bool,
        typer.Option(
            "--fatal-exif-date-match/--no-fatal-exif-date-match",
            help="Treat EXIF date mismatch warnings as errors (default: enabled).",
        ),
    ] = True,
    check_naming: Annotated[
        bool,
        typer.Option(
            "--check-naming/--no-check-naming",
            help="Enable/disable album naming convention checks (default: enabled).",
        ),
    ] = True,
    check_date_part_collision: Annotated[
        bool,
        typer.Option(
            "--check-date-part-collision/--no-check-date-part-collision",
            help="Enable/disable cross-album date collision detection (default: enabled).",
        ),
    ] = True,
    check_exif_date_match: Annotated[
        bool,
        typer.Option(
            "--check-exif-date-match/--no-check-exif-date-match",
            help="Enable/disable EXIF timestamp vs album date validation (default: enabled).",
        ),
    ] = True,
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
    refresh_jpeg: Annotated[
        bool,
        typer.Option(
            "--refresh-jpeg",
            help="Refresh {name}-jpg/ from {name}-img/ for all media sources.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", "-n", help="Print what would happen without modifying files."
        ),
    ] = False,
) -> None:
    """Fix all albums under a directory or from an explicit list."""
    from ..fsprotocol import discover_all_albums

    if not fix_id and not new_id and not refresh_jpeg:
        typer.echo(
            "No fix specified. Run photree albums fix --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)

    if refresh_jpeg:
        _check_sips_or_exit()

    if fix_id and not new_id:
        albums, display_base = _resolve_batch_albums_with(
            base_dir, album_dirs, discover_all_albums
        )
    else:
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
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink, symlink, or copy.",
        ),
    ] = LinkMode.HARDLINK,
    refresh_combined: Annotated[
        bool,
        typer.Option(
            "--refresh-combined",
            help="Rebuild main-img/ and main-vid/ from orig/edit, then regenerate main-jpg/.",
        ),
    ] = False,
    refresh_jpeg: Annotated[
        bool,
        typer.Option(
            "--refresh-jpeg",
            help="Refresh main-jpg/ from main-img/ (re-convert all HEIC→JPEG).",
        ),
    ] = False,
    rm_upstream: Annotated[
        bool,
        typer.Option(
            "--rm-upstream",
            help="Propagate deletions from browsing dirs (main-jpg, main-vid) to upstream dirs.",
        ),
    ] = False,
    rm_orphan: Annotated[
        bool,
        typer.Option(
            "--rm-orphan",
            help="Delete edited and main files that have no corresponding orig file.",
        ),
    ] = False,
    prefer_higher_quality_when_dups: Annotated[
        bool,
        typer.Option(
            "--prefer-higher-quality-when-dups", help="Delete lower-quality duplicates."
        ),
    ] = False,
    rm_orphan_sidecar: Annotated[
        bool,
        typer.Option(
            "--rm-orphan-sidecar",
            help="Delete AAE sidecar files that have no matching media file.",
        ),
    ] = False,
    rm_miscategorized: Annotated[
        bool,
        typer.Option(
            "--rm-miscategorized", help="Delete files in the wrong directory."
        ),
    ] = False,
    rm_miscategorized_safe: Annotated[
        bool,
        typer.Option(
            "--rm-miscategorized-safe",
            help="Delete miscategorized files only if they already exist in the correct directory.",
        ),
    ] = False,
    mv_miscategorized: Annotated[
        bool,
        typer.Option(
            "--mv-miscategorized",
            help="Move files in the wrong directory to the correct one.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", "-n", help="Print what would happen without modifying files."
        ),
    ] = False,
) -> None:
    """Apply fix-ios to all iOS albums under a directory or from an explicit list."""
    _validate_fix_flags(
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
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink, symlink, or copy.",
        ),
    ] = LinkMode.HARDLINK,
    check: Annotated[
        bool,
        typer.Option(
            "--check/--no-check",
            help="Run integrity checks before optimizing (default: enabled).",
        ),
    ] = True,
    checksum: Annotated[
        bool,
        typer.Option(
            "--checksum/--no-checksum",
            help="Enable/disable SHA-256 checksum verification (default: enabled).",
        ),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", "-n", help="Print what would happen without modifying files."
        ),
    ] = False,
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
# Image Capture batch import
# ---------------------------------------------------------------------------


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
