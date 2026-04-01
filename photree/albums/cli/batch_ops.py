"""Shared batch operations for gallery and albums commands.

These functions implement the core logic for batch operations on multiple
albums. Both ``gallery`` and ``albums`` CLI commands delegate to them.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer

from ...album import (
    fixes as album_fixes,
    naming as album_naming,
    optimize as album_optimize,
    output as album_output,
    preflight as album_preflight,
    stats as album_stats,
)
from ...album.exif import try_start_exiftool
from ...album.preflight import output as preflight_output
from ...album.stats import output as stats_output
from ...fs import (
    AlbumMetadata,
    LinkMode,
    discover_media_sources,
    display_path,
    format_album_external_id,
    generate_album_id,
    load_album_metadata,
    save_album_metadata,
)
from ...gallery.index import find_duplicate_album_ids
from ...album.ios_fixes import run_fix_ios
from ...album.output import format_fix_ios_result
from ...fs import discover_potential_albums
from ...clicommons.console import console, err_console
from ...clicommons.progress import BatchProgressBar


def display_name(album_dir: Path, base_dir: Path | None, cwd: Path) -> str:
    """Human-readable album name relative to *base_dir* or *cwd*."""
    if base_dir is not None:
        return str(album_dir.relative_to(base_dir))

    return str(display_path(album_dir, cwd))


def run_batch_init(
    albums: list[Path],
    display_base: Path | None,
    *,
    dry_run: bool = False,
) -> None:
    """Shared implementation for albums init."""
    cwd = Path.cwd()

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")

    progress = BatchProgressBar(
        total=len(albums), description="Initializing", done_description="init"
    )
    initialized = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = display_name(album_dir, display_base, cwd)
        progress.on_start(album_name)

        try:
            metadata = load_album_metadata(album_dir)
            if metadata is not None:
                progress.on_end(
                    album_name,
                    success=False,
                    error_labels=(
                        f"already initialized: {format_album_external_id(metadata.id)}",
                    ),
                )
                failed_albums.append(album_dir)
                continue

            if dry_run:
                progress.on_end(album_name, success=True)
            else:
                generated_id = generate_album_id()
                save_album_metadata(album_dir, AlbumMetadata(id=generated_id))
                progress.on_end(album_name, success=True)
            initialized += 1
        except Exception:
            progress.on_end(album_name, success=False)
            failed_albums.append(album_dir)

    progress.stop()

    typer.echo(
        f"\nDone. {initialized} album(s) initialized, {len(failed_albums)} failed."
    )

    if failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in failed_albums:
            err_console.print(
                f'  photree album init --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)


def run_batch_list_albums(
    albums: list[Path],
    display_base: Path | None,
    *,
    metadata: bool = True,
    output_format: str = "text",
    output_file: Path | None = None,
) -> None:
    """Shared implementation for list-albums / albums list."""
    import csv
    import sys

    from ...album.naming import parse_album_name

    cwd = Path.cwd()

    if not albums:
        typer.echo("No albums found.", err=output_format == "csv")
        raise typer.Exit(code=0)

    # All albums must have IDs
    missing_id = [a for a in albums if load_album_metadata(a) is None]
    if missing_id:
        err_console.print("Albums with missing IDs found:")
        for p in missing_id:
            err_console.print(f"  {display_path(p, cwd)}")
        err_console.print(
            "\nRun 'photree gallery fix --id' to generate missing album IDs."
        )
        raise typer.Exit(code=1)

    if output_format == "csv":
        out = (
            open(output_file, "w", encoding="utf-8", newline="")
            if output_file
            else sys.stdout
        )
        try:
            writer = csv.writer(out)
            writer.writerow(
                [
                    "id",
                    "path",
                    "date",
                    "part",
                    "series",
                    "title",
                    "location",
                    "tags",
                    "media_sources",
                ]
            )
            for album_dir in albums:
                rel_path = display_name(album_dir, display_base, cwd)
                album_meta = load_album_metadata(album_dir)
                external_id = (
                    format_album_external_id(album_meta.id)
                    if album_meta is not None
                    else ""
                )
                parsed = parse_album_name(album_dir.name)
                media_sources = discover_media_sources(album_dir)
                ms_desc = ", ".join(
                    f"{c.name} ({c.media_source_type})" for c in media_sources
                )
                if parsed is not None:
                    tags = "private" if parsed.private else ""
                    writer.writerow(
                        [
                            external_id,
                            rel_path,
                            parsed.date,
                            parsed.part or "",
                            parsed.series or "",
                            parsed.title,
                            parsed.location or "",
                            tags,
                            ms_desc,
                        ]
                    )
                else:
                    writer.writerow(
                        [
                            external_id,
                            rel_path,
                            "",
                            "",
                            "",
                            album_dir.name,
                            "",
                            "",
                            ms_desc,
                        ]
                    )
        finally:
            if output_file:
                out.close()
        return

    typer.echo(f"Found {len(albums)} album(s).\n")

    for album_dir in albums:
        name = display_name(album_dir, display_base, cwd)
        typer.echo(name)

        if metadata:
            album_meta = load_album_metadata(album_dir)
            if album_meta is not None:
                typer.echo(f"  id: {format_album_external_id(album_meta.id)}")
            else:
                typer.echo("  id: (missing)")

            parsed = parse_album_name(album_dir.name)
            media_sources = discover_media_sources(album_dir)

            if parsed is not None:
                parts = [f"date={parsed.date}"]
                if parsed.part is not None:
                    parts.append(f"part={parsed.part}")
                if parsed.series is not None:
                    parts.append(f"series={parsed.series}")
                parts.append(f"title={parsed.title}")
                if parsed.location is not None:
                    parts.append(f"location={parsed.location}")
                if parsed.private:
                    parts.append("private")
                typer.echo(f"  {', '.join(parts)}")
            else:
                typer.echo("  (name not parseable)")

            if media_sources:
                ms_desc = ", ".join(
                    f"{c.name} ({c.media_source_type})" for c in media_sources
                )
                typer.echo(f"  media sources: {ms_desc}")


def run_batch_check(
    albums: list[Path],
    display_base: Path | None,
    *,
    checksum: bool = True,
    fatal_warnings: bool = False,
    fatal_sidecar_arg: bool = False,
    fatal_exif_date_match: bool = True,
    check_naming: bool = True,
    check_date_part_collision: bool = True,
    check_exif_date_match: bool = True,
) -> None:
    """Shared implementation for gallery check / albums check."""
    cwd = Path.cwd()

    # System checks (once)
    sips_available = album_preflight.check_sips_available()
    exiftool = try_start_exiftool() if check_exif_date_match else None
    exiftool_available = exiftool is not None
    typer.echo("System Checks:")
    console.print(preflight_output.sips_check(sips_available))
    console.print(preflight_output.exiftool_check(exiftool_available))
    if not sips_available:
        typer.echo("")
        err_console.print(preflight_output.sips_troubleshoot())
        raise typer.Exit(code=1)

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")
    else:
        typer.echo("")

    # Check each album
    fatal_sidecar = fatal_warnings or fatal_sidecar_arg
    fatal_exif = fatal_warnings or fatal_exif_date_match

    progress = BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    )
    passed = 0
    warned = 0
    failed_albums: list[Path] = []

    try:
        for album_dir in albums:
            album_name = display_name(album_dir, display_base, cwd)

            progress.on_start(album_name)
            result = album_preflight.run_album_check(
                album_dir,
                sips_available=sips_available,
                exiftool=exiftool,
                checksum=checksum,
                check_naming_flag=check_naming,
            )

            # Include external album ID in the result line when available
            id_check = result.album_id_check
            album_label = (
                f"{album_name} ({format_album_external_id(id_check.album_id)})"
                if id_check is not None and id_check.album_id is not None
                else album_name
            )

            album_ok = result.success and not result.has_fatal_warnings(
                fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
            )
            err_labels = (
                *result.error_labels,
                *result.fatal_warning_labels(
                    fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
                ),
            )
            warn_labels = result.non_fatal_warning_labels(
                fatal_sidecar=fatal_sidecar, fatal_exif=fatal_exif
            )
            if album_ok:
                progress.on_end(album_label, success=True, warning_labels=warn_labels)
                passed += 1
                if result.has_warnings:
                    warned += 1
            else:
                progress.on_end(
                    album_label,
                    success=False,
                    error_labels=err_labels,
                    warning_labels=warn_labels,
                )
                failed_albums.append(album_dir)
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)

    progress.stop()

    # Batch naming checks (date collisions across all albums)
    if check_naming and check_date_part_collision:
        parsed_albums = [
            (album.name, parsed)
            for album in albums
            if (parsed := album_naming.parse_album_name(album.name)) is not None
        ]
        batch_naming = album_naming.check_batch_date_collisions(parsed_albums)
        typer.echo("")
        console.print(preflight_output.format_batch_naming_issues(batch_naming))
        if not batch_naming.success:
            colliding_names = {
                name for _, names in batch_naming.date_collisions for name in names
            }
            failed_albums.extend(a for a in albums if a.name in colliding_names)

    # Duplicate album ID detection
    duplicates = find_duplicate_album_ids(albums)
    typer.echo("")
    if duplicates:
        for aid, paths in duplicates.items():
            ext_id = format_album_external_id(aid)
            err_console.print(f"[red]\u2717[/red] duplicate album id: {ext_id}")
            for p in paths:
                err_console.print(f"    {display_path(p, cwd)}")
        failed_albums.extend(p for paths in duplicates.values() for p in paths)
    else:
        console.print(f"{album_output.CHECK} no duplicate album ids")

    # Summary
    console.print(album_output.batch_check_summary(passed, len(failed_albums), warned))

    if failed_albums:
        extra_flags = "".join(
            [
                " --fatal-warnings" if fatal_warnings else "",
                " --fatal-sidecar" if fatal_sidecar_arg else "",
                " --no-fatal-exif-date-match" if not fatal_exif_date_match else "",
            ]
        )
        err_console.print("\nTo investigate failures:")
        for album_dir in sorted(set(failed_albums)):
            err_console.print(
                f'  photree album check --album-dir "{display_path(album_dir, cwd)}"{extra_flags}'
            )
        raise typer.Exit(code=1)


def run_batch_fix(
    albums: list[Path],
    display_base: Path | None,
    *,
    fix_id: bool = False,
    new_id: bool = False,
    refresh_jpeg: bool = False,
    dry_run: bool = False,
) -> None:
    """Shared implementation for gallery fix / albums fix."""
    cwd = Path.cwd()

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")

    progress = BatchProgressBar(
        total=len(albums), description="Fixing", done_description="fix"
    )
    fixed = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = display_name(album_dir, display_base, cwd)
        progress.on_start(album_name)

        try:
            needs_id = (fix_id and load_album_metadata(album_dir) is None) or new_id
            if needs_id and not dry_run:
                save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))

            if refresh_jpeg:
                sources = discover_media_sources(album_dir)
                for ms in sources:
                    if (album_dir / ms.img_dir).is_dir():
                        album_fixes.refresh_jpeg(album_dir, ms, dry_run=dry_run)

            progress.on_end(album_name, success=True)
            fixed += 1
        except Exception:
            progress.on_end(album_name, success=False)
            failed_albums.append(album_dir)

    progress.stop()

    typer.echo(f"\nDone. {fixed} album(s) fixed, {len(failed_albums)} failed.")

    if failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in failed_albums:
            err_console.print(
                f'  photree album fix --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)


def run_batch_optimize(
    albums: list[Path],
    display_base: Path | None,
    *,
    link_mode: LinkMode,
    check: bool = True,
    checksum: bool = True,
    dry_run: bool = False,
) -> None:
    """Shared implementation for gallery optimize / albums optimize."""
    cwd = Path.cwd()

    sips_available = True
    if check:
        sips_available = album_preflight.check_sips_available()
        typer.echo("System Checks:")
        console.print(preflight_output.sips_check(sips_available))
        if not sips_available:
            typer.echo("")
            err_console.print(preflight_output.sips_troubleshoot())
            raise typer.Exit(code=1)

    if not albums:
        typer.echo("\nNo iOS albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} iOS album(s).\n")
    else:
        typer.echo("")

    progress = BatchProgressBar(
        total=len(albums), description="Optimizing", done_description="optimize"
    )
    optimized = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = display_name(album_dir, display_base, cwd)
        progress.on_start(album_name)

        if check:
            check_result = album_preflight.run_album_check(
                album_dir,
                sips_available=sips_available,
                exiftool=None,
                checksum=checksum,
                check_naming_flag=False,
            )
            if not check_result.success:
                progress.on_end(album_name, success=False)
                failed_albums.append(album_dir)
                continue

        album_optimize.optimize_album(album_dir, link_mode=link_mode, dry_run=dry_run)
        progress.on_end(album_name, success=True)
        optimized += 1

    progress.stop()

    console.print(album_output.batch_optimize_summary(optimized, len(failed_albums)))

    if failed_albums:
        err_console.print("\nTo investigate failures:")
        for album_dir in failed_albums:
            err_console.print(
                f'  photree album check --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)


def run_batch_fix_ios(
    albums: list[Path],
    display_base: Path | None,
    *,
    link_mode: LinkMode,
    dry_run: bool = False,
    refresh_combined: bool = False,
    refresh_jpeg: bool = False,
    rm_upstream: bool = False,
    rm_orphan: bool = False,
    rm_orphan_sidecar: bool = False,
    prefer_higher_quality_when_dups: bool = False,
    rm_miscategorized: bool = False,
    rm_miscategorized_safe: bool = False,
    mv_miscategorized: bool = False,
) -> None:
    """Shared implementation for gallery fix-ios / albums fix-ios."""
    cwd = Path.cwd()

    if not albums:
        typer.echo("No iOS albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"Found {len(albums)} iOS album(s).\n")

    progress = BatchProgressBar(
        total=len(albums), description="Fixing", done_description="fix-ios"
    )
    fixed = 0
    failed_albums: list[Path] = []
    album_reports: list[tuple[str, str]] = []

    for album_dir in albums:
        album_name = display_name(album_dir, display_base, cwd)
        progress.on_start(album_name)

        try:
            result = run_fix_ios(
                album_dir,
                link_mode=link_mode,
                dry_run=dry_run,
                log_cwd=cwd,
                refresh_combined_flag=refresh_combined,
                refresh_jpeg_flag=refresh_jpeg,
                rm_upstream=rm_upstream,
                rm_orphan=rm_orphan,
                rm_orphan_sidecar=rm_orphan_sidecar,
                prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
                rm_miscategorized=rm_miscategorized,
                rm_miscategorized_safe=rm_miscategorized_safe,
                mv_miscategorized=mv_miscategorized,
            )
            progress.on_end(album_name, success=True)
            fixed += 1
            lines = format_fix_ios_result(result)
            if lines:
                album_reports.append((album_name, "\n".join(lines)))
        except Exception:
            progress.on_end(album_name, success=False)
            failed_albums.append(album_dir)

    progress.stop()

    if album_reports:
        typer.echo("")
        for album_name, report in album_reports:
            typer.echo(f"{album_name}:")
            typer.echo(report, color=True)

    console.print(album_output.batch_fix_ios_summary(fixed, len(failed_albums)))

    if failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in failed_albums:
            err_console.print(
                f'  photree album fix-ios --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)


def run_batch_stats(
    albums: list[Path],
    display_base: Path | None,
) -> None:
    """Shared implementation for gallery stats / albums stats."""
    from ...album.naming import parse_album_name

    cwd = Path.cwd()

    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    unparseable = [a for a in albums if parse_album_name(a.name) is None]
    if unparseable:
        err_console.print(
            f"{len(unparseable)} album(s) have unparseable names. "
            f"Run photree albums check to identify and fix naming issues:"
        )
        for album_dir in unparseable:
            err_console.print(f"  {display_path(album_dir, cwd)}")
        raise typer.Exit(code=1)

    if display_base is not None:
        typer.echo(f"Found {len(albums)} album(s).\n")

    progress = BatchProgressBar(
        total=len(albums), description="Computing stats", done_description="stats"
    )

    album_stats_list: list[album_stats.AlbumStats] = []
    for album_dir in albums:
        album_name = display_name(album_dir, display_base, cwd)
        progress.on_start(album_name)
        stats = album_stats.compute_album_stats(album_dir)
        album_stats_list.append(stats)
        progress.on_end(album_name, success=True)

    progress.stop()

    result = album_stats.gallery_stats_from_album_stats(album_stats_list)
    typer.echo("")
    console.print(stats_output.format_gallery_stats(result))


def run_batch_rename_from_csv(
    index: dict[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Shared implementation for gallery rename-from-csv / albums rename-from-csv."""
    import csv as csv_mod

    from ...gallery import plan_renames_from_csv
    from ...gallery.batch_rename import (
        RenameCollisionError,
        check_rename_collisions,
        execute_renames,
    )

    cwd = Path.cwd()

    # Read CSV
    with open(csv_file, encoding="utf-8") as f:
        rows = list(csv_mod.DictReader(f))

    if not rows:
        typer.echo("CSV is empty. Nothing to rename.")
        raise typer.Exit(code=0)

    # Plan renames
    actions, errors = plan_renames_from_csv(rows, index)

    if errors:
        for err in errors:
            err_console.print(f"  {err}")
        raise typer.Exit(code=1)

    if not actions:
        typer.echo(f"{len(rows)} row(s) in CSV. Nothing to rename.")
        raise typer.Exit(code=0)

    # Check for collisions
    try:
        check_rename_collisions(actions)
    except RenameCollisionError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc

    # Display plan
    typer.echo(f"{len(rows)} row(s) in CSV, {len(actions)} change(s).\n")

    for action in actions:
        typer.echo(f"  {display_path(action.album_path, cwd)}")
        typer.echo(f"  \u2192 {action.new_name}")
        typer.echo()

    if dry_run:
        typer.echo(f"[dry run] {len(actions)} album(s) would be renamed.")
    else:
        count = execute_renames(actions)
        typer.echo(f"Renamed {count} album(s).")


# ---------------------------------------------------------------------------
# Album resolution helpers
# ---------------------------------------------------------------------------


def resolve_check_batch_albums(
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


def resolve_batch_albums(
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


def resolve_init_batch_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
) -> tuple[list[Path], Path | None]:
    """Resolve album list for init commands.

    Uses :func:`discover_potential_albums` which finds directories with
    media sources regardless of whether ``.photree/album.yaml`` exists.
    """
    return _resolve_batch_albums_with(base_dir, album_dirs, discover_potential_albums)


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
