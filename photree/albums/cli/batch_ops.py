"""Shared batch CLI wrappers for gallery and albums commands.

Each ``run_batch_*`` function creates progress bars, calls the
corresponding command handler, displays results, and handles
``typer.Exit``. Both ``gallery`` and ``albums`` CLI commands delegate
to these wrappers.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer

from ...album import (
    preflight as album_preflight,
)
from ...album.fix.output import batch_fix_summary
from ...album.fix.ios.output import batch_fix_ios_summary
from ...album.optimize import batch_optimize_summary
from ...album.preflight import output as preflight_output
from ...album.preflight.output import batch_check_summary
from ...album.stats import output as stats_output
from ...common.exif import try_start_exiftool
from ...common.formatting import CHECK
from ...album.store.fs import (
    discover_media_sources,
    discover_potential_albums,
    load_album_metadata,
)
from ...album.store.protocol import format_album_external_id
from ...common.fs import display_path
from ...fsprotocol import LinkMode
from ...clihelpers.console import console, err_console
from ...clihelpers.progress import BatchProgressBar
from ..cmd_handler.init import batch_init
from ..cmd_handler.check import batch_check
from ..cmd_handler.fix import batch_fix
from ..cmd_handler.optimize import batch_optimize
from ..cmd_handler.fix_ios import batch_fix_ios
from ..cmd_handler.stats import batch_stats
from ..cmd_handler.rename import batch_rename_from_csv


def display_name(album_dir: Path, base_dir: Path | None, cwd: Path) -> str:
    """Human-readable album name relative to *base_dir* or *cwd*."""
    if base_dir is not None:
        return str(album_dir.relative_to(base_dir))

    return str(display_path(album_dir, cwd))


def _make_display_fn(display_base: Path | None, cwd: Path) -> Callable[[Path], str]:
    return lambda album_dir: display_name(album_dir, display_base, cwd)


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

    result = batch_init(
        albums,
        dry_run=dry_run,
        display_fn=_make_display_fn(display_base, cwd),
        on_start=progress.on_start,
        on_end=lambda name, success, errors: progress.on_end(
            name, success=success, error_labels=errors
        ),
    )

    progress.stop()

    typer.echo(
        f"\nDone. {result.initialized} album(s) initialized, {len(result.failed_albums)} failed."
    )

    if result.failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in result.failed_albums:
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

    fatal_sidecar = fatal_warnings or fatal_sidecar_arg
    fatal_exif = fatal_warnings or fatal_exif_date_match

    progress = BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    )

    try:
        result = batch_check(
            albums,
            sips_available=sips_available,
            exiftool=exiftool,
            checksum=checksum,
            fatal_sidecar=fatal_sidecar,
            fatal_exif=fatal_exif,
            check_naming=check_naming,
            check_date_part_collision=check_date_part_collision,
            display_fn=_make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors, warnings: progress.on_end(
                name,
                success=success,
                error_labels=errors,
                warning_labels=warnings,
            ),
        )
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)

    progress.stop()

    # Display naming issues
    if result.naming_result is not None:
        typer.echo("")
        console.print(preflight_output.format_batch_naming_issues(result.naming_result))

    # Display duplicate IDs
    typer.echo("")
    if result.duplicate_ids:
        for aid, paths in result.duplicate_ids.items():
            ext_id = format_album_external_id(aid)
            err_console.print(f"[red]\u2717[/red] duplicate album id: {ext_id}")
            for p in paths:
                err_console.print(f"    {display_path(p, cwd)}")
    else:
        console.print(f"{CHECK} no duplicate album ids")

    # Summary
    console.print(
        batch_check_summary(result.passed, len(result.failed_albums), result.warned)
    )

    if result.failed_albums:
        extra_flags = "".join(
            [
                " --fatal-warnings" if fatal_warnings else "",
                " --fatal-sidecar" if fatal_sidecar_arg else "",
                " --no-fatal-exif-date-match" if not fatal_exif_date_match else "",
            ]
        )
        err_console.print("\nTo investigate failures:")
        for album_dir in sorted(set(result.failed_albums)):
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
    link_mode: LinkMode = LinkMode.HARDLINK,
    refresh_browsable: bool = False,
    refresh_jpeg: bool = False,
    rm_upstream: bool = False,
    rm_orphan: bool = False,
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

    result = batch_fix(
        albums,
        fix_id=fix_id,
        new_id=new_id,
        link_mode=link_mode,
        refresh_browsable=refresh_browsable,
        refresh_jpeg=refresh_jpeg,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        dry_run=dry_run,
        display_fn=_make_display_fn(display_base, cwd),
        on_start=progress.on_start,
        on_end=lambda name, success: progress.on_end(name, success=success),
    )

    progress.stop()

    if result.album_reports:
        typer.echo("")
        for album_name, report in result.album_reports:
            typer.echo(f"{album_name}:")
            typer.echo(report, color=True)

    console.print(batch_fix_summary(result.fixed, len(result.failed_albums)))

    if result.failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in result.failed_albums:
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

    result = batch_optimize(
        albums,
        link_mode=link_mode,
        check=check,
        checksum=checksum,
        sips_available=sips_available,
        dry_run=dry_run,
        display_fn=_make_display_fn(display_base, cwd),
        on_start=progress.on_start,
        on_end=lambda name, success: progress.on_end(name, success=success),
    )

    progress.stop()

    console.print(batch_optimize_summary(result.optimized, len(result.failed_albums)))

    if result.failed_albums:
        err_console.print("\nTo investigate failures:")
        for album_dir in result.failed_albums:
            err_console.print(
                f'  photree album check --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)


def run_batch_fix_ios(
    albums: list[Path],
    display_base: Path | None,
    *,
    dry_run: bool = False,
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

    result = batch_fix_ios(
        albums,
        dry_run=dry_run,
        rm_orphan_sidecar=rm_orphan_sidecar,
        prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
        rm_miscategorized=rm_miscategorized,
        rm_miscategorized_safe=rm_miscategorized_safe,
        mv_miscategorized=mv_miscategorized,
        display_fn=_make_display_fn(display_base, cwd),
        on_start=progress.on_start,
        on_end=lambda name, success: progress.on_end(name, success=success),
    )

    progress.stop()

    if result.album_reports:
        typer.echo("")
        for album_name, report in result.album_reports:
            typer.echo(f"{album_name}:")
            typer.echo(report, color=True)

    console.print(batch_fix_ios_summary(result.fixed, len(result.failed_albums)))

    if result.failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in result.failed_albums:
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

    result = batch_stats(
        albums,
        display_fn=_make_display_fn(display_base, cwd),
        on_start=progress.on_start,
        on_end=lambda name, success: progress.on_end(name, success=success),
    )

    progress.stop()

    typer.echo("")
    console.print(stats_output.format_gallery_stats(result))


def run_batch_rename_from_csv(
    index: dict[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Shared implementation for gallery rename-from-csv / albums rename-from-csv."""
    from ...gallery.renamer import RenameCollisionError

    cwd = Path.cwd()

    try:
        result = batch_rename_from_csv(index, csv_file, dry_run=dry_run)
    except RenameCollisionError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=1) from exc

    if result.errors:
        for err in result.errors:
            err_console.print(f"  {err}")
        raise typer.Exit(code=1)

    if not result.actions:
        if result.row_count == 0:
            typer.echo("CSV is empty. Nothing to rename.")
        else:
            typer.echo(f"{result.row_count} row(s) in CSV. Nothing to rename.")
        raise typer.Exit(code=0)

    # Display plan
    typer.echo(f"{result.row_count} row(s) in CSV, {len(result.actions)} change(s).\n")

    for action in result.actions:
        typer.echo(f"  {display_path(action.album_path, cwd)}")
        typer.echo(f"  \u2192 {action.new_name}")
        typer.echo()

    if dry_run:
        typer.echo(f"[dry run] {len(result.actions)} album(s) would be renamed.")
    else:
        typer.echo(f"Renamed {result.renamed} album(s).")


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
    """Resolve album list for archive-based commands.

    Uses :func:`discover_archive_albums` which finds albums with iOS
    (``ios-*/``) or std (``std-*/``) archive directories.
    """
    return _resolve_batch_albums_with(
        base_dir, album_dirs, album_preflight.discover_archive_albums
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
