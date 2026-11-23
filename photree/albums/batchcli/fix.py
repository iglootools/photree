"""``albums fix`` / ``albums fix-ios`` wrappers."""

from pathlib import Path

import typer

from photree.album.fix.output import batch_fix_summary
from photree.albums.batchcli.failures import (
    album_reports_block,
    exit_if_no_albums,
    exit_with_failures,
)
from photree.albums.batchcli.resolution import make_display_fn
from photree.albums.cmd_handler.fix import batch_fix
from photree.albums.cmd_handler.fix_ios import batch_fix_ios
from photree.clihelpers.console import console
from photree.clihelpers.progress import BatchProgressBar
from photree.common.formatting import format_dry_run, format_flags


def _print_reports(reports: tuple[tuple[str, str], ...]) -> None:
    if reports:
        typer.echo("")
        typer.echo(album_reports_block(reports), color=True)


def run_batch_fix(
    albums: list[Path],
    display_base: Path | None,
    *,
    fix_id: bool = False,
    new_id: bool = False,
    rm_upstream: bool = False,
    rm_orphan: bool = False,
    dry_run: bool = False,
    force: bool = False,
    cwd: Path,
) -> None:
    """Shared implementation for gallery fix / albums fix."""
    exit_if_no_albums(albums, display_base)

    with BatchProgressBar(
        total=len(albums),
        description="Fixing",
        done_description="fix",
    ) as progress:
        result = batch_fix(
            albums,
            fix_id=fix_id,
            new_id=new_id,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
            dry_run=dry_run,
            force=force,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=progress.on_end,
        )

    _print_reports(result.album_reports)
    console.print(
        format_dry_run(
            batch_fix_summary(result.fixed, len(result.failures), dry_run=dry_run),
            dry_run=dry_run,
            markup=True,
        ),
    )
    # The single-album retry must carry the same fixes, or it only prints
    # "No fix specified".
    retry_flags = format_flags(
        [
            ("--id", fix_id),
            ("--new-id", new_id),
            ("--rm-upstream", rm_upstream),
            ("--rm-orphan", rm_orphan),
            ("--force", force),
            ("--dry-run", dry_run),
        ],
    )
    exit_with_failures(result.failures, "fix", cwd, extra_flags=retry_flags)


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
    cwd: Path,
) -> None:
    """Shared implementation for gallery fix-ios / albums fix-ios."""
    exit_if_no_albums(albums, display_base, noun="iOS album")

    with BatchProgressBar(
        total=len(albums),
        description="Fixing",
        done_description="fix-ios",
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
            on_end=progress.on_end,
        )

    _print_reports(result.album_reports)
    console.print(
        format_dry_run(
            batch_fix_summary(result.fixed, len(result.failures), dry_run=dry_run),
            dry_run=dry_run,
            markup=True,
        ),
    )
    exit_with_failures(
        result.failures,
        "fix-ios",
        cwd,
        extra_flags=format_flags(
            [
                ("--rm-orphan-sidecar", rm_orphan_sidecar),
                (
                    "--prefer-higher-quality-when-dups",
                    prefer_higher_quality_when_dups,
                ),
                ("--rm-miscategorized", rm_miscategorized),
                ("--rm-miscategorized-safe", rm_miscategorized_safe),
                ("--mv-miscategorized", mv_miscategorized),
                ("--dry-run", dry_run),
            ],
        ),
    )
