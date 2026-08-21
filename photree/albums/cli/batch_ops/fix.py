"""``albums fix`` / ``albums fix-ios`` wrappers."""

from __future__ import annotations

from pathlib import Path

import typer

from ....album.fix.ios.output import batch_fix_ios_summary
from ....album.fix.output import batch_fix_summary
from ....clihelpers.console import console, err_console
from ....clihelpers.progress import BatchProgressBar
from ....common.fs import display_path
from ....fsprotocol import LinkMode
from ...cmd_handler.fix import batch_fix
from ...cmd_handler.fix_ios import batch_fix_ios
from ..ops import make_display_fn
from .failures import batch_failures_report


def run_batch_fix(
    albums: list[Path],
    display_base: Path | None,
    *,
    fix_id: bool = False,
    new_id: bool = False,
    link_mode: LinkMode = LinkMode.HARDLINK,
    rm_upstream: bool = False,
    rm_orphan: bool = False,
    dry_run: bool = False,
    max_workers: int | None = None,
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
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
            dry_run=dry_run,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
            max_workers=max_workers,
        )

    if result.album_reports:
        typer.echo("")
        for album_name, report in result.album_reports:
            typer.echo(f"{album_name}:")
            typer.echo(report, color=True)

    console.print(batch_fix_summary(result.fixed, len(result.failed_albums)))

    if result.failed_albums:
        err_console.print(batch_failures_report(result.failures, cwd))
        err_console.print("\nTo investigate failures:")
        for album_dir in result.failed_albums:
            err_console.print(
                f'  photree album fix --album-dir "{display_path(album_dir, cwd)}"'
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
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    if result.album_reports:
        typer.echo("")
        for album_name, report in result.album_reports:
            typer.echo(f"{album_name}:")
            typer.echo(report, color=True)

    console.print(batch_fix_ios_summary(result.fixed, len(result.failed_albums)))

    if result.failed_albums:
        err_console.print(batch_failures_report(result.failures, cwd))
        err_console.print("\nTo investigate failures:")
        for album_dir in result.failed_albums:
            err_console.print(
                f'  photree album fix-ios --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)
