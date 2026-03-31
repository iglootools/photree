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
    preflight as album_preflight,
)
from ..fsprotocol import (
    GALLERY_YAML,
    GalleryMetadata,
    LinkMode,
    PHOTREE_DIR,
    discover_all_albums,
    display_path,
    resolve_gallery_dir,
    resolve_link_mode,
    save_gallery_metadata,
)
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
from .console import err_console

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
    current_csv: Annotated[
        Path,
        typer.Argument(
            help="CSV with current album state (from gallery list-albums --format csv).",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    desired_csv: Annotated[
        Path,
        typer.Argument(
            help="CSV with desired album state (edited copy of current).",
            exists=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    base_dir: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Root directory (base for relative paths in CSV).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show what would be renamed without making changes.",
        ),
    ] = False,
) -> None:
    """Rename albums by diffing current vs desired CSV files (from list-albums --format csv).

    Only the series, title, and location columns may differ between the two files.
    """
    import csv
    import unicodedata

    from ..album.naming import ParsedAlbumName, reconstruct_name

    def _nfc(s: str) -> str:
        return unicodedata.normalize("NFC", s)

    def _name_from_row(row: dict[str, str]) -> str:
        parsed = ParsedAlbumName(
            date=row["date"],
            part=row["part"] or None,
            private="private" in row.get("tags", ""),
            series=row["series"] or None,
            title=row["title"],
            location=row["location"] or None,
        )
        return reconstruct_name(parsed)

    with open(current_csv, encoding="utf-8") as f:
        current_rows = {r["path"]: r for r in csv.DictReader(f)}

    with open(desired_csv, encoding="utf-8") as f:
        desired_rows = {r["path"]: r for r in csv.DictReader(f)}

    if not desired_rows:
        typer.echo("Desired CSV is empty.")
        raise typer.Exit(code=0)

    # Fields that must not differ between current and desired
    immutable_fields = ("path", "date", "part", "tags", "media_sources")

    renames: list[tuple[Path, str]] = []
    errors: list[str] = []

    for path, desired in desired_rows.items():
        current = current_rows.get(path)
        if current is None:
            errors.append(f"Path not found in current CSV: {path}")
            continue

        # Safety: only title and location may be changed
        for field in immutable_fields:
            if _nfc(current.get(field, "")) != _nfc(desired.get(field, "")):
                errors.append(
                    f"{path}: field '{field}' was modified "
                    f"({current.get(field, '')!r} → {desired.get(field, '')!r}). "
                    f"Only 'series', 'title', and 'location' may be changed."
                )

        # Only process rows where series, title, or location actually changed
        series_changed = _nfc(current.get("series", "")) != _nfc(
            desired.get("series", "")
        )
        title_changed = _nfc(current.get("title", "")) != _nfc(desired.get("title", ""))
        location_changed = _nfc(current.get("location", "")) != _nfc(
            desired.get("location", "")
        )
        if not series_changed and not title_changed and not location_changed:
            continue

        album_path = base_dir / path
        if not album_path.is_dir():
            errors.append(f"Directory not found: {path}")
            continue

        desired_name = _name_from_row(desired)
        renames.append((album_path, desired_name))

    if errors:
        for err in errors:
            typer.echo(f"  {err}", err=True)
        raise typer.Exit(code=1)

    if not renames:
        typer.echo(
            f"Current: {len(current_rows)} rows, "
            f"desired: {len(desired_rows)} rows. Nothing to rename."
        )
        raise typer.Exit(code=0)

    # Check for collisions (resolve() handles case-insensitive macOS)
    renamed_resolved = {album_path.resolve() for album_path, _ in renames}
    for album_path, desired_name in renames:
        target = album_path.parent / desired_name
        if (
            target.exists()
            and target.resolve() != album_path.resolve()
            and target.resolve() not in renamed_resolved
        ):
            typer.echo(
                f"Collision: {album_path.relative_to(base_dir)} → {desired_name} "
                f"conflicts with {target.relative_to(base_dir)}",
                err=True,
            )
            raise typer.Exit(code=1)

    # Display plan
    typer.echo(
        f"Current: {len(current_rows)} rows, desired: {len(desired_rows)} rows, "
        f"changes: {len(renames)}"
    )
    typer.echo()

    for album_path, desired_name in renames:
        typer.echo(f"  {album_path.relative_to(base_dir)}")
        typer.echo(f"  → {desired_name}")
        typer.echo()

    if dry_run:
        typer.echo(f"[dry run] {len(renames)} album(s) would be renamed.")
    else:
        for album_path, desired_name in renames:
            new_path = album_path.parent / desired_name
            album_path.rename(new_path)

        typer.echo(f"Renamed {len(renames)} album(s).")


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


# Re-register the export batch command from export_cmd
from .export_cmd import export_all_cmd  # noqa: E402

gallery_app.command("export")(export_all_cmd)
