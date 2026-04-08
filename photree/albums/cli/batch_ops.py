"""Shared batch CLI wrappers for gallery and albums commands.

Each ``run_batch_*`` function creates progress bars, calls the
corresponding command handler, displays results, and handles
``typer.Exit``. Both ``gallery`` and ``albums`` CLI commands delegate
to these wrappers.

Album resolution helpers live in :mod:`ops`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ...album import (
    check as album_check,
)
from ...album.check import output as preflight_output
from ...album.check.output import batch_check_summary
from ...album.fix.output import batch_fix_summary
from ...album.fix.ios.output import batch_fix_ios_summary
from ...album.optimize import batch_optimize_summary
from ...album.stats import output as stats_output
from ...common.exif import try_start_exiftool
from ...common.formatting import CHECK
from ...album.store.media_sources_discovery import discover_media_sources
from ...album.store.metadata import load_album_metadata
from ...album.id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
)
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
from ..cmd_handler.refresh import batch_refresh
from ..cmd_handler.rename import batch_rename_from_csv
from .ops import display_name, make_display_fn


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

    with BatchProgressBar(
        total=len(albums), description="Initializing", done_description="init"
    ) as progress:
        result = batch_init(
            albums,
            dry_run=dry_run,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

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


def run_batch_refresh(
    albums: list[Path],
    display_base: Path | None,
    *,
    dry_run: bool = False,
) -> None:
    """Shared implementation for albums refresh / gallery refresh."""
    cwd = Path.cwd()

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")

    with BatchProgressBar(
        total=len(albums), description="Refreshing", done_description="refresh"
    ) as progress:
        result = batch_refresh(
            albums,
            dry_run=dry_run,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    typer.echo(
        f"\nDone. {result.refreshed} album(s) refreshed,"
        f" {len(result.failed_albums)} failed."
    )

    if result.failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in result.failed_albums:
            err_console.print(
                f'  photree album refresh --album-dir "{display_path(album_dir, cwd)}"'
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
    sips_available = album_check.check_sips_available()
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

    with BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    ) as progress:
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
                display_fn=make_display_fn(display_base, cwd),
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

    if result.duplicate_media_ids:
        for mid, paths in result.duplicate_media_ids.items():
            ext_id = format_image_external_id(mid)
            err_console.print(f"[red]\u2717[/red] duplicate media id: {ext_id}")
            for p in paths:
                err_console.print(f"    {display_path(p, cwd)}")
    else:
        console.print(f"{CHECK} no duplicate media ids")

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

    with BatchProgressBar(
        total=len(albums), description="Fixing", done_description="fix"
    ) as progress:
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
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success: progress.on_end(name, success=success),
        )

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
        sips_available = album_check.check_sips_available()
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

    with BatchProgressBar(
        total=len(albums), description="Optimizing", done_description="optimize"
    ) as progress:
        result = batch_optimize(
            albums,
            link_mode=link_mode,
            check=check,
            checksum=checksum,
            sips_available=sips_available,
            dry_run=dry_run,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success: progress.on_end(name, success=success),
        )

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

    with BatchProgressBar(
        total=len(albums), description="Fixing", done_description="fix-ios"
    ) as progress:
        result = batch_fix_ios(
            albums,
            dry_run=dry_run,
            rm_orphan_sidecar=rm_orphan_sidecar,
            prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
            rm_miscategorized=rm_miscategorized,
            rm_miscategorized_safe=rm_miscategorized_safe,
            mv_miscategorized=mv_miscategorized,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success: progress.on_end(name, success=success),
        )

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
    *,
    gallery_dir: Path | None = None,
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

    with BatchProgressBar(
        total=len(albums), description="Computing stats", done_description="stats"
    ) as progress:
        result = batch_stats(
            albums,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success: progress.on_end(name, success=success),
        )

    # Add collection stats if gallery context is available
    if gallery_dir is not None:
        from ...collection.stats import compute_gallery_collection_stats
        from ...album.stats.models import GalleryStats

        col_stats = compute_gallery_collection_stats(gallery_dir)
        result = GalleryStats(
            album_count=result.album_count,
            by_album=result.by_album,
            aggregate=result.aggregate,
            unique_media_source_names=result.unique_media_source_names,
            by_year=result.by_year,
            collection_stats=col_stats,
        )

    typer.echo("")
    console.print(stats_output.format_gallery_stats(result))


def run_batch_rename_from_csv(
    index: dict[str, Path],
    csv_file: Path,
    *,
    dry_run: bool = False,
) -> None:
    """Shared implementation for gallery rename-from-csv / albums rename-from-csv."""
    from ..renamer import RenameCollisionError

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


def run_batch_list_media(
    albums: list[Path],
    display_base: Path | None,
    *,
    output_format: str = "text",
    output_file: Path | None = None,
) -> None:
    """Shared implementation for albums list-media / gallery list-media."""
    import csv
    import sys

    from ...album.store.media_metadata import load_media_metadata

    cwd = Path.cwd()

    if not albums:
        typer.echo("No albums found.", err=output_format == "csv")
        raise typer.Exit(code=0)

    if output_format == "csv":
        out = (
            open(output_file, "w", encoding="utf-8", newline="")
            if output_file
            else sys.stdout
        )
        try:
            writer = csv.writer(out)
            writer.writerow(["album_id", "media_source", "type", "id", "key"])
            for album_dir in albums:
                album_meta = load_album_metadata(album_dir)
                album_ext_id = (
                    format_album_external_id(album_meta.id)
                    if album_meta is not None
                    else ""
                )
                media_meta = load_media_metadata(album_dir)
                if media_meta is None:
                    continue
                for source_name, source in media_meta.media_sources.items():
                    for mid, key in source.images.items():
                        writer.writerow(
                            [
                                album_ext_id,
                                source_name,
                                "image",
                                format_image_external_id(mid),
                                key,
                            ]
                        )
                    for mid, key in source.videos.items():
                        writer.writerow(
                            [
                                album_ext_id,
                                source_name,
                                "video",
                                format_video_external_id(mid),
                                key,
                            ]
                        )
        finally:
            if output_file:
                out.close()
        return

    for album_dir in albums:
        name = display_name(album_dir, display_base, cwd)
        album_meta = load_album_metadata(album_dir)
        album_ext_id = (
            format_album_external_id(album_meta.id) if album_meta is not None else ""
        )
        media_meta = load_media_metadata(album_dir)
        if media_meta is None or not media_meta.media_sources:
            continue

        typer.echo(f"{name}")
        if album_ext_id:
            typer.echo(f"  id: {album_ext_id}")
        for source_name, source in media_meta.media_sources.items():
            typer.echo(f"  {source_name}:")
            if source.images:
                typer.echo("    images:")
                for mid, key in source.images.items():
                    typer.echo(f"      {format_image_external_id(mid)}: {key}")
            if source.videos:
                typer.echo("    videos:")
                for mid, key in source.videos.items():
                    typer.echo(f"      {format_video_external_id(mid)}: {key}")
