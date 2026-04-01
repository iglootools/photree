"""CLI commands for the ``photree gallery`` sub-app.

Gallery commands operate on all albums within a gallery (resolved via
``--gallery-dir`` or ``.photree/gallery.yaml`` in parent directories).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ..fs import (
    GALLERY_YAML,
    GalleryMetadata,
    LinkMode,
    PHOTREE_DIR,
    discover_albums,
    display_path,
    format_album_external_id,
    load_gallery_metadata,
    resolve_link_mode,
    save_gallery_metadata,
)
from ..gallery.importer import (
    BatchImportValidationError,
    compute_target_dir,
    validate_batch_import,
)
from ..album.ios_fixes import FixIosValidationError, validate_fix_flags
from .album_cmd import _check_sips_or_exit
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
    LINK_MODE_OPTION,
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
    resolve_batch_albums,
    resolve_check_batch_albums,
    run_batch_check,
    run_batch_fix,
    run_batch_fix_ios,
    run_batch_list_albums,
    run_batch_optimize,
    run_batch_rename_from_csv,
    run_batch_stats,
)
from .console import err_console
from .gallery_ops import (
    build_index_or_exit,
    print_single_import_result,
    resolve_gallery_or_exit,
    resolve_import_all_albums,
    run_batch_import,
    run_batch_post_import_check,
    run_single_import,
    validate_single_import,
)

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
    cwd = Path.cwd()
    is_cwd = gallery_dir.resolve() == cwd.resolve()
    gallery_flag = "" if is_cwd else f' -g "{display_path(gallery_dir, cwd)}"'
    typer.echo(
        f"Created {display_path(gallery_yaml, cwd)} (link-mode: {link_mode})\n"
        "\nNext steps:\n"
        f"  photree gallery import -a <album-dir>{gallery_flag}\n"
        f"  photree gallery check{gallery_flag}\n"
        f"  photree gallery stats{gallery_flag}\n"
        f"  photree gallery export --share-dir <share-dir>{gallery_flag}"
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
    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()
    metadata = load_gallery_metadata(resolved / PHOTREE_DIR / GALLERY_YAML)
    albums = discover_albums(resolved)

    typer.echo(f"Gallery: {display_path(resolved, cwd)}")
    typer.echo(f"  link-mode: {metadata.link_mode}")
    typer.echo(f"  albums: {len(albums)}")


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
    """List all albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
    run_batch_list_albums(
        albums,
        display_base,
        metadata=metadata,
        output_format=output_format,
        output_file=output_file,
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
    checksum: CHECKSUM_OPTION = True,
    fatal_warnings: FATAL_WARNINGS_OPTION = False,
    fatal_sidecar_arg: FATAL_SIDECAR_OPTION = False,
    fatal_exif_date_match: FATAL_EXIF_DATE_MATCH_OPTION = True,
    check_naming: CHECK_NAMING_OPTION = True,
    check_date_part_collision: CHECK_DATE_PART_COLLISION_OPTION = True,
    check_exif_date_match: CHECK_EXIF_DATE_MATCH_OPTION = True,
) -> None:
    """Check all albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
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
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
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

    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)

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
    link_mode: LINK_MODE_OPTION = None,
    check: CHECK_BEFORE_OPTION = True,
    checksum: CHECKSUM_OPTION = True,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Optimize all iOS albums in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_batch_albums(resolved, None)
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
    link_mode: LINK_MODE_OPTION = None,
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
    """Apply fix-ios to all iOS albums in the gallery."""
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
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_batch_albums(resolved, None)
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
    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()

    # Build album index
    index = build_index_or_exit(resolved, cwd)

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

    run_batch_rename_from_csv(index.id_to_path, csv_file, dry_run=dry_run)


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
    resolved = resolve_gallery_or_exit(gallery_dir)
    albums, display_base = resolve_check_batch_albums(resolved, None)
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
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()
    index = build_index_or_exit(resolved_gallery, cwd)

    validate_single_import(album_dir, index, resolved_gallery, cwd)
    result = run_single_import(album_dir, resolved_gallery, resolved_lm, dry_run)
    print_single_import_result(result, cwd, dry_run)


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

    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()

    albums = resolve_import_all_albums(base_dir, album_dirs)
    index = build_index_or_exit(resolved_gallery, cwd)

    try:
        validate_batch_import(albums, index, resolved_gallery)
    except BatchImportValidationError as exc:
        err_console.print(f"Cannot import — {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Found {len(albums)} album(s).\n")
    typer.echo("Import:")
    imported, failed_albums = run_batch_import(
        albums, resolved_gallery, resolved_lm, dry_run
    )

    if not dry_run and imported > 0:
        typer.echo("\nPost-Import Check:")
        imported_targets = [
            compute_target_dir(resolved_gallery, a.name)
            for a in albums
            if a not in failed_albums
        ]
        check_failed = run_batch_post_import_check(imported_targets, cwd)
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
    from ..album.exporter.settings import (
        ExportSettingsError,
        resolve_export_settings,
        validate_export_settings,
    )
    from ..config import ConfigError
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
