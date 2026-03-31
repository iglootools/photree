"""CLI commands for the ``photree gallery`` sub-app.

Gallery commands operate on all albums within a gallery (resolved via
``--gallery-dir`` or ``.photree/gallery.yaml`` in parent directories).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Optional

import typer

from ..album import (
    output as album_output,
    preflight as album_preflight,
)
from ..album.exif import try_start_exiftool
from ..album.naming import (
    AlbumNamingResult,
    check_album_naming,
    parse_album_name,
)
from ..album.output.preflight import format_naming_checks
from ..fsprotocol import (
    AlbumShareLayout,
    GALLERY_YAML,
    GalleryMetadata,
    LinkMode,
    PHOTREE_DIR,
    ShareDirectoryLayout,
    discover_all_albums,
    discover_albums,
    display_path,
    format_album_external_id,
    load_album_metadata,
    load_gallery_metadata,
    resolve_gallery_dir,
    resolve_link_mode,
    save_gallery_metadata,
)
from ..gallery import (
    AlbumIndex,
    MissingAlbumIdError,
    build_album_id_to_path_index,
)
from ..gallery import importer as gallery_importer
from ..gallery.importer import compute_target_dir
from .album_cmd import (
    _check_sips_or_exit,
    _validate_fix_flags,
)
from .batch_ops import (
    run_batch_check,
    run_batch_fix,
    run_batch_fix_ios,
    run_batch_list_albums,
    run_batch_optimize,
    run_batch_stats,
)
from .console import console, err_console
from .progress import BatchProgressBar, StageProgressBar

gallery_app = typer.Typer(
    name="gallery",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)


@gallery_app.command("init")
def init_cmd(
    gallery_dir: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    link_mode: Annotated[
        LinkMode,
        typer.Option(
            "--link-mode",
            help="Default link mode for optimize and other link-mode operations.",
        ),
    ] = LinkMode.HARDLINK,
) -> None:
    """Initialize gallery metadata (.photree/gallery.yaml)."""
    gallery_yaml = gallery_dir / PHOTREE_DIR / GALLERY_YAML
    if gallery_yaml.is_file():
        typer.echo(
            f"Gallery already initialized: {display_path(gallery_yaml, Path.cwd())}\n"
            "Edit the file directly to change settings.",
            err=True,
        )
        raise typer.Exit(code=1)

    save_gallery_metadata(gallery_dir, GalleryMetadata(link_mode=link_mode))
    typer.echo(
        f"Created {display_path(gallery_yaml, Path.cwd())} (link-mode: {link_mode})"
    )


@gallery_app.command("show")
def show_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Display gallery metadata."""
    resolved = _resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()
    metadata = load_gallery_metadata(resolved / PHOTREE_DIR / GALLERY_YAML)
    albums = discover_albums(resolved)

    typer.echo(f"Gallery: {display_path(resolved, cwd)}")
    typer.echo(f"  link-mode: {metadata.link_mode}")
    typer.echo(f"  albums: {len(albums)}")


def _resolve_check_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], Path | None]:
    """Resolve album list for check commands (all album types).

    Uses :func:`discover_albums` which detects iOS albums, ``.album``
    sentinels, and leaf directories.
    """
    return _resolve_batch_albums_with(
        base_dir, album_dirs, album_preflight.discover_albums
    )


def _resolve_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], Path | None]:
    """Resolve album list for iOS-specific commands.

    Uses :func:`discover_ios_albums` which only finds albums with an
    ``ios/`` subdirectory.
    """
    return _resolve_batch_albums_with(
        base_dir, album_dirs, album_preflight.discover_ios_albums
    )


def _resolve_batch_albums_with(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    discover_fn: Callable[[Path], list[Path]],
) -> tuple[list[Path], Path | None]:
    """Resolve album list from mutually exclusive --dir / --album-dir options.

    Returns ``(albums, display_base)`` where *display_base* is the base
    directory when --dir was used (for relative display names), or ``None``
    when --album-dir was used (display names are CWD-relative).
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn

    if base_dir is not None and album_dirs is not None:
        typer.echo(
            "--dir and --album-dir are mutually exclusive.",
            err=True,
        )
        raise typer.Exit(code=1)

    if album_dirs is not None:
        return (album_dirs, None)

    # --dir mode (explicit or default)
    resolved_base = base_dir if base_dir is not None else Path(".").resolve()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Resolving album list...", total=None)
        albums = discover_fn(resolved_base)
    return (albums, resolved_base)


# ---------------------------------------------------------------------------
# Gallery commands — resolve gallery dir, discover albums, delegate to shared logic
# ---------------------------------------------------------------------------


def _resolve_gallery_or_exit(gallery_dir: Path | None) -> Path:
    """Resolve gallery directory or exit with a clear error."""
    try:
        return resolve_gallery_dir(gallery_dir)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc


def _build_index_or_exit(gallery_dir: Path, cwd: Path) -> AlbumIndex:
    """Build the gallery album index, or exit on missing IDs."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Building album index...", total=None)
            return build_album_id_to_path_index(gallery_dir)
    except MissingAlbumIdError as exc:
        err_console.print("Albums with missing IDs found:")
        for p in exc.albums:
            err_console.print(f"  {display_path(p, cwd)}")
        err_console.print(
            "\nRun 'photree gallery fix --id' to generate missing album IDs."
        )
        raise typer.Exit(code=1) from exc


@gallery_app.command("list-albums")
def list_albums_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
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
    """List all albums in the gallery."""
    resolved = _resolve_gallery_or_exit(gallery_dir)
    albums, display_base = _resolve_check_batch_albums(resolved, None)
    run_batch_list_albums(
        albums, display_base, metadata=metadata, output_format=output_format
    )


@gallery_app.command("check")
def check_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
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
            "--fatal-sidecar", help="Treat missing-sidecar warnings as errors."
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
    """Check all albums in the gallery."""
    resolved = _resolve_gallery_or_exit(gallery_dir)
    albums, display_base = _resolve_check_batch_albums(resolved, None)
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


@gallery_app.command("fix")
def fix_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
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
    """Fix all albums in the gallery."""
    if not fix_id and not new_id and not refresh_jpeg:
        typer.echo(
            "No fix specified. Run photree gallery fix --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)

    if refresh_jpeg:
        _check_sips_or_exit()

    resolved = _resolve_gallery_or_exit(gallery_dir)
    if fix_id and not new_id:
        albums, display_base = _resolve_batch_albums_with(
            resolved, None, discover_all_albums
        )
    else:
        albums, display_base = _resolve_check_batch_albums(resolved, None)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        refresh_jpeg=refresh_jpeg,
        dry_run=dry_run,
    )


@gallery_app.command("optimize")
def optimize_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    link_mode: Annotated[
        LinkMode | None,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = None,
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
    """Optimize all iOS albums in the gallery."""
    resolved = _resolve_gallery_or_exit(gallery_dir)
    albums, display_base = _resolve_batch_albums(resolved, None)
    run_batch_optimize(
        albums,
        display_base,
        link_mode=resolve_link_mode(link_mode, resolved),
        check=check,
        checksum=checksum,
        dry_run=dry_run,
    )


@gallery_app.command("fix-ios")
def fix_ios_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    link_mode: Annotated[
        LinkMode | None,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = None,
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
    """Apply fix-ios to all iOS albums in the gallery."""
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
    resolved = _resolve_gallery_or_exit(gallery_dir)
    albums, display_base = _resolve_batch_albums(resolved, None)
    run_batch_fix_ios(
        albums,
        display_base,
        link_mode=resolve_link_mode(link_mode, resolved),
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


@gallery_app.command("rename-from-csv")
def rename_from_csv_cmd(
    csv_file: Annotated[
        Path,
        typer.Argument(
            help="CSV with desired album state (from list-albums --format csv, edited).",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show what would be renamed without making changes.",
        ),
    ] = False,
) -> None:
    """Rename albums from a CSV file (from list-albums --format csv, edited).

    Uses the album ID to look up each album in the gallery, then compares the
    current series, title, and location against the CSV values. Only albums
    where a mutable field changed are renamed. Immutable fields (date, part,
    tags) are preserved from the current on-disk album name.
    """
    import csv

    from ..gallery import plan_renames_from_csv

    resolved = _resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()

    # Build album index
    index = _build_index_or_exit(resolved, cwd)

    # Check for duplicate IDs in gallery
    if index.duplicates:
        err_console.print("Cannot rename — duplicate album IDs in gallery:")
        for aid, paths in index.duplicates.items():
            err_console.print(f"  {format_album_external_id(aid)}:")
            for p in paths:
                err_console.print(f"    {display_path(p, cwd)}")
        err_console.print(
            "\nResolve duplicates first with 'photree gallery fix --new-id'."
        )
        raise typer.Exit(code=1)

    # Read CSV
    with open(csv_file, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        typer.echo("CSV is empty. Nothing to rename.")
        raise typer.Exit(code=0)

    # Plan renames
    actions, errors = plan_renames_from_csv(rows, index.id_to_path)

    if errors:
        for err in errors:
            err_console.print(f"  {err}")
        raise typer.Exit(code=1)

    if not actions:
        typer.echo(f"{len(rows)} row(s) in CSV. Nothing to rename.")
        raise typer.Exit(code=0)

    # Check for collisions (resolve() handles case-insensitive macOS)
    renamed_resolved = {a.album_path.resolve() for a in actions}
    for action in actions:
        target = action.album_path.parent / action.new_name
        if (
            target.exists()
            and target.resolve() != action.album_path.resolve()
            and target.resolve() not in renamed_resolved
        ):
            err_console.print(
                f"Collision: {action.current_name} → {action.new_name} "
                f"conflicts with existing directory"
            )
            raise typer.Exit(code=1)

    # Display plan
    typer.echo(f"{len(rows)} row(s) in CSV, {len(actions)} change(s).\n")

    for action in actions:
        typer.echo(f"  {display_path(action.album_path, cwd)}")
        typer.echo(f"  → {action.new_name}")
        typer.echo()

    if dry_run:
        typer.echo(f"[dry run] {len(actions)} album(s) would be renamed.")
    else:
        for action in actions:
            new_path = action.album_path.parent / action.new_name
            action.album_path.rename(new_path)

        typer.echo(f"Renamed {len(actions)} album(s).")


@gallery_app.command("stats")
def stats_cmd(
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Show aggregated disk usage and content statistics for all albums in the gallery."""
    resolved = _resolve_gallery_or_exit(gallery_dir)
    albums, display_base = _resolve_check_batch_albums(resolved, None)
    run_batch_stats(albums, display_base)


# ---------------------------------------------------------------------------
# Gallery import commands
# ---------------------------------------------------------------------------


@gallery_app.command("import")
def import_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to import into the gallery.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    link_mode: Annotated[
        LinkMode | None,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Import an existing album directory into the gallery.

    Copies the album to <gallery>/albums/YYYY/<album-name>/, generates a
    missing album ID, refreshes JPEGs if stale, optimizes links, and runs
    integrity checks.
    """
    resolved_gallery = _resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()

    # Build gallery index for pre-import ID uniqueness check
    index = _build_index_or_exit(resolved_gallery, cwd)

    # Check source album ID uniqueness against gallery
    source_meta = load_album_metadata(album_dir)
    if source_meta is not None and source_meta.id in index.id_to_path:
        existing = index.id_to_path[source_meta.id]
        err_console.print(
            f"Cannot import — album ID already exists in gallery:\n"
            f"  source: {display_path(album_dir, cwd)}\n"
            f"  existing: {display_path(existing, cwd)}\n"
            f"  id: {format_album_external_id(source_meta.id)}"
        )
        raise typer.Exit(code=1)

    # Validate album name before doing anything
    naming_issues = check_album_naming(album_dir.name)
    if naming_issues:
        parsed = parse_album_name(album_dir.name)
        naming_result = AlbumNamingResult(
            parsed=parsed, issues=naming_issues, exif_check=None
        )
        typer.echo("Naming Convention Check:")
        console.print(format_naming_checks(naming_result))
        err_console.print(
            "\nAlbum name does not follow naming conventions. "
            "Rename the album directory before importing."
        )
        raise typer.Exit(code=1)

    # Check target doesn't exist
    target = compute_target_dir(resolved_gallery, album_dir.name)
    if target.exists():
        err_console.print(
            f"Target already exists: {display_path(target, cwd)}\n"
            "Cannot import — an album with the same name is already in the gallery."
        )
        raise typer.Exit(code=1)

    typer.echo("Import:")
    progress = StageProgressBar(
        total=4,
        labels={
            "copy": "Copying album",
            "id": "Checking album ID",
            "jpeg": "Refreshing JPEGs",
            "optimize": "Optimizing links",
        },
    )
    try:
        result = gallery_importer.import_album(
            source_dir=album_dir,
            gallery_dir=resolved_gallery,
            link_mode=resolved_lm,
            dry_run=dry_run,
            on_stage_start=progress.on_start,
            on_stage_end=progress.on_end,
        )
    except ValueError as exc:
        progress.stop()
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        progress.stop()

    # Post-import metadata
    if not dry_run:
        meta = load_album_metadata(result.target_dir)
        if meta is not None:
            typer.echo(f"Album ID: {format_album_external_id(meta.id)}")
    typer.echo(f"Target: {display_path(result.target_dir, cwd)}")

    # Run album check on the imported copy
    if not dry_run:
        typer.echo("\nPost-Import Check:")
        check_result = album_preflight.run_album_preflight(result.target_dir)
        console.print(album_output.format_album_preflight_checks(check_result))
        if not check_result.success:
            err_console.print(
                f'\nTo investigate: photree album check --album-dir "{display_path(result.target_dir, cwd)}"'
            )
            raise typer.Exit(code=1)


@gallery_app.command("import-all")
def import_all_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to scan for album subdirectories.",
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
    gallery_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    link_mode: Annotated[
        LinkMode | None,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Batch import album directories into the gallery.

    Either scan --dir for immediate subdirectories, or provide explicit
    album directories via --album-dir (repeatable). Copies each album to
    <gallery>/albums/YYYY/<album-name>/, generates missing IDs, refreshes
    JPEGs, optimizes links, and runs gallery-wide checks.
    """
    if base_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    resolved_gallery = _resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()

    # Resolve album list
    if album_dirs is not None:
        albums = album_dirs
    else:
        scan_dir = base_dir if base_dir is not None else Path(".").resolve()
        albums = sorted(p for p in scan_dir.iterdir() if p.is_dir())

    if not albums:
        typer.echo("No album directories found.")
        raise typer.Exit(code=0)

    # Build gallery index for pre-import ID uniqueness check
    index = _build_index_or_exit(resolved_gallery, cwd)

    # Pre-validate: source album ID uniqueness
    source_metas = [
        (a, meta) for a in albums if (meta := load_album_metadata(a)) is not None
    ]

    # Check source IDs against gallery
    gallery_conflicts = [
        (a, meta, index.id_to_path[meta.id])
        for a, meta in source_metas
        if meta.id in index.id_to_path
    ]
    if gallery_conflicts:
        err_console.print("Cannot import — album ID(s) already exist in gallery:")
        for src, meta, existing in gallery_conflicts:
            err_console.print(
                f"  {src.name} ({format_album_external_id(meta.id)})"
                f" → {display_path(existing, cwd)}"
            )
        raise typer.Exit(code=1)

    # Check for duplicate IDs among source albums
    import itertools

    sorted_sources = sorted(source_metas, key=lambda t: t[1].id)
    source_grouped = {
        aid: [p for p, _ in group]
        for aid, group in itertools.groupby(sorted_sources, key=lambda t: t[1].id)
    }
    source_dups = {
        aid: paths for aid, paths in source_grouped.items() if len(paths) > 1
    }
    if source_dups:
        err_console.print("Cannot import — duplicate album IDs among source albums:")
        for aid, paths in source_dups.items():
            err_console.print(f"  {format_album_external_id(aid)}:")
            for p in paths:
                err_console.print(f"    {display_path(p, cwd)}")
        raise typer.Exit(code=1)

    # Pre-validate: check all targets before importing any
    target_conflicts = [
        (a, compute_target_dir(resolved_gallery, a.name))
        for a in albums
        if compute_target_dir(resolved_gallery, a.name).exists()
    ]
    if target_conflicts:
        err_console.print("Cannot import — target(s) already exist:")
        for src, tgt in target_conflicts:
            err_console.print(f"  {src.name} → {display_path(tgt, cwd)}")
        raise typer.Exit(code=1)

    typer.echo(f"Found {len(albums)} album(s).\n")
    typer.echo("Import:")

    progress = BatchProgressBar(
        total=len(albums), description="Importing", done_description="import"
    )
    imported = 0
    failed_albums: list[Path] = []

    for album_path in albums:
        album_name = album_path.name
        progress.on_start(album_name)

        try:
            gallery_importer.import_album(
                source_dir=album_path,
                gallery_dir=resolved_gallery,
                link_mode=resolved_lm,
                dry_run=dry_run,
            )
            progress.on_end(album_name, success=True)
            imported += 1
        except (ValueError, OSError) as exc:
            progress.on_end(album_name, success=False, error_labels=(str(exc)[:60],))
            failed_albums.append(album_path)

    progress.stop()

    # Post-import gallery check
    if not dry_run and imported > 0:
        typer.echo("\nPost-Import Check:")
        imported_targets = [
            compute_target_dir(resolved_gallery, a.name)
            for a in albums
            if a not in failed_albums
        ]

        sips_available = album_preflight.check_sips_available()
        exiftool = try_start_exiftool()
        check_progress = BatchProgressBar(
            total=len(imported_targets),
            description="Checking",
            done_description="check",
        )
        check_failed: list[Path] = []
        try:
            for target_dir in imported_targets:
                target_name = display_path(target_dir, cwd)
                check_progress.on_start(str(target_name))
                check_result = album_preflight.run_album_check(
                    target_dir,
                    sips_available=sips_available,
                    exiftool=exiftool,
                )
                if check_result.success:
                    check_progress.on_end(str(target_name), success=True)
                else:
                    check_progress.on_end(
                        str(target_name),
                        success=False,
                        error_labels=check_result.error_labels,
                    )
                    check_failed.append(target_dir)
        finally:
            if exiftool is not None:
                exiftool.__exit__(None, None, None)
        check_progress.stop()

        if check_failed:
            err_console.print("\nTo investigate failures:")
            for target_dir in check_failed:
                err_console.print(
                    f'  photree album check --album-dir "{display_path(target_dir, cwd)}"'
                )

    typer.echo(f"\nDone. {imported} album(s) imported, {len(failed_albums)} failed.")
    if failed_albums:
        raise typer.Exit(code=1)


# Re-register the export batch command — defined here to avoid circular import
# with albums_cmd (which imports from gallery_cmd).
from ..album.exporter import export_batch as _export_batch  # noqa: E402
from ..album.exporter import output as _export_output  # noqa: E402


@gallery_app.command("export")
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
    share_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--share-dir",
            "-s",
            help="Base directory to export into (subdirectories with album names are created).",
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile",
            "-p",
            help="Exporter profile name from config.",
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
    share_layout: Annotated[
        Optional[ShareDirectoryLayout],
        typer.Option(
            "--share-layout",
            help="Share layout: flat (default) or albums.",
        ),
    ] = None,
    album_layout: Annotated[
        Optional[AlbumShareLayout],
        typer.Option(
            "--album-layout",
            help="Export layout: main-jpg (default), main, or all.",
        ),
    ] = None,
    link_mode: Annotated[
        Optional[LinkMode],
        typer.Option(
            "--link-mode",
            help="How to create main files in all layout: hardlink (default), symlink, or copy.",
        ),
    ] = None,
) -> None:
    """Batch export multiple albums to a shared directory.

    Either scan --dir for albums or provide explicit album directories via
    --album-dir (repeatable). The two options are mutually exclusive.
    """
    from .album_cmd import _resolve_export_settings, _validate_export_settings
    from .progress import BatchProgressBar

    cwd = Path.cwd()

    if base_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    settings = _resolve_export_settings(
        profile_name=profile,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config_path=config,
    )
    _validate_export_settings(settings)

    resolved_base = (
        None
        if album_dirs is not None
        else (base_dir if base_dir is not None else Path(".").resolve())
    )

    albums = (
        list(album_dirs)
        if album_dirs is not None
        else _export_batch.discover_albums(resolved_base)  # type: ignore[arg-type]
    )

    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    progress = BatchProgressBar(
        total=len(albums), description="Exporting", done_description="export"
    )

    result = _export_batch.run_batch_export(
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

    typer.echo(_export_output.batch_export_summary(result.exported, len(result.failed)))

    if result.failed:
        typer.echo("\nFailed albums:", err=True)
        for album_dir_path, error in result.failed:
            typer.echo(f"  {display_path(album_dir_path, cwd)}: {error}", err=True)
        raise typer.Exit(code=1)
