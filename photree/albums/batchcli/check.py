"""``albums check`` / ``gallery check`` wrapper."""

from dataclasses import dataclass
from pathlib import Path

import typer

from photree.album.check.output import album as album_output
from photree.album.id import format_album_external_id, format_image_external_id
from photree.albums.batchcli.failures import batch_failures_report, investigate_commands
from photree.albums.batchcli.resolution import make_display_fn
from photree.albums.cmd_handler import BatchFailure
from photree.albums.cmd_handler.check import (
    BatchCheckResult,
    CrossAlbumCheckResult,
    batch_check,
    check_cross_album,
    compute_batch_check_summary,
    refresh_exif_caches,
)
from photree.albums.output import check as batch_output
from photree.albums.output.check import batch_check_summary
from photree.clihelpers.console import console, err_console
from photree.clihelpers.progress import BatchProgressBar, run_with_spinner
from photree.clihelpers.sysdeps import CHECK_DEPS, EXIF_DEPS, require_system_deps
from photree.common.exif import ExifTagReader, exiftool_session
from photree.common.sysdeps import WhichFn
from photree.foundation.gallery_metadata import resolve_link_mode


@dataclass(frozen=True)
class _CheckFlags:
    checksum: bool
    fatal_warnings: bool
    fatal_sidecar_arg: bool
    fatal_exif_date_match: bool
    check_naming: bool
    check_date_part_collision: bool

    @property
    def fatal_sidecar(self) -> bool:
        return self.fatal_warnings or self.fatal_sidecar_arg

    @property
    def fatal_exif(self) -> bool:
        return self.fatal_warnings or self.fatal_exif_date_match

    def retry_flags(self) -> str:
        return batch_output.batch_check_retry_flags(
            fatal_warnings=self.fatal_warnings,
            fatal_sidecar=self.fatal_sidecar_arg,
            fatal_exif_date_match=self.fatal_exif_date_match,
        )


def _conclude(*, success: bool, exit_on_failure: bool) -> bool:
    if not success and exit_on_failure:
        raise typer.Exit(code=1)
    return success


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
    refresh_exif_cache: bool = False,
    exit_on_failure: bool = True,
    which: WhichFn,
    cwd: Path,
) -> bool:
    """
    Shared implementation for gallery check / albums check.

    Returns ``True`` when every album passed (or there were none). With
    ``exit_on_failure`` (the default) a failed run raises ``typer.Exit(1)``
    and an empty one ``typer.Exit(0)``; pass ``False`` to get the verdict
    back and keep going (``gallery check`` then checks collections too). A
    missing ``sips`` always exits: it is a property of the machine.
    """
    flags = _CheckFlags(
        checksum,
        fatal_warnings,
        fatal_sidecar_arg,
        fatal_exif_date_match,
        check_naming,
        check_date_part_collision,
    )
    # --refresh-exif-cache cannot degrade without exiftool, so it is required.
    require_system_deps(
        (*CHECK_DEPS, *EXIF_DEPS) if refresh_exif_cache else CHECK_DEPS,
        which=which,
    )
    checked = _run_per_album_checks(
        albums,
        display_base,
        flags,
        cwd,
        check_exif_date_match=check_exif_date_match,
        refresh_exif_cache=refresh_exif_cache,
        which=which,
    )
    if checked is None:
        typer.echo("\nNo albums found.")
        if exit_on_failure:
            raise typer.Exit(code=0)
        return True
    result, refresh_failures = checked

    cross_album = run_with_spinner(
        "Running cross-album checks...",
        lambda: check_cross_album(
            albums,
            check_date_collisions=flags.check_naming
            and flags.check_date_part_collision,
        ),
    )
    _print_cross_album(cross_album, cwd)
    success = _report(albums, result, cross_album, refresh_failures, flags, cwd=cwd)
    return _conclude(success=success, exit_on_failure=exit_on_failure)


def _run_per_album_checks(
    albums: list[Path],
    display_base: Path | None,
    flags: _CheckFlags,
    cwd: Path,
    *,
    check_exif_date_match: bool,
    refresh_exif_cache: bool,
    which: WhichFn,
) -> tuple[BatchCheckResult, tuple[BatchFailure, ...]] | None:
    """
    Optionally refresh EXIF caches, then check each album.

    Returns ``None`` when there are no albums. The exiftool process lives
    exactly as long as this call, so no exit path can leak it.
    """
    with exiftool_session(
        enabled=check_exif_date_match or refresh_exif_cache,
        which=which,
    ) as et:
        if not refresh_exif_cache:
            console.print(album_output.exiftool_check(available=et is not None))
        if not albums:
            return None
        refresh_failures = (
            _refresh_exif_caches(albums, et, cwd) if refresh_exif_cache else ()
        )
        typer.echo(f"\nFound {len(albums)} album(s).\n" if display_base else "")
        return _check_albums(albums, display_base, flags, et, cwd), refresh_failures


def _refresh_exif_caches(
    albums: list[Path],
    exiftool: ExifTagReader | None,
    cwd: Path,
) -> tuple[BatchFailure, ...]:
    """Refresh every album's EXIF cache, printing the albums that failed."""
    typer.echo("\nRefreshing EXIF cache...")
    failures = refresh_exif_caches(albums, exiftool)
    if failures:
        err_console.print(batch_failures_report(failures, cwd))
    return failures


def _check_albums(
    albums: list[Path],
    display_base: Path | None,
    flags: _CheckFlags,
    exiftool: ExifTagReader | None,
    cwd: Path,
) -> BatchCheckResult:
    with BatchProgressBar(
        total=len(albums),
        description="Checking",
        done_description="check",
    ) as progress:
        return batch_check(
            albums,
            # require_system_deps exited already if sips were missing.
            sips_available=True,
            exiftool=exiftool,
            link_mode_for=lambda album_dir: resolve_link_mode(None, album_dir),
            checksum=flags.checksum,
            fatal_sidecar=flags.fatal_sidecar,
            fatal_exif=flags.fatal_exif,
            check_naming=flags.check_naming,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=progress.on_end,
        )


def _print_cross_album(cross_album: CrossAlbumCheckResult, cwd: Path) -> None:
    typer.echo("\nCross-album checks:")
    if cross_album.naming_result is not None:
        console.print(
            album_output.format_batch_naming_issues(cross_album.naming_result),
        )
    for kind, duplicates, format_id in (
        ("album", cross_album.duplicate_album_ids, format_album_external_id),
        ("media", cross_album.duplicate_media_ids, format_image_external_id),
    ):
        if duplicates:
            err_console.print(
                batch_output.duplicate_ids_report(
                    kind,
                    {k: list(v) for k, v in duplicates.items()},
                    cwd,
                    format_id,
                ),
            )
        else:
            console.print(batch_output.no_duplicate_ids_line(kind))


def _report(
    albums: list[Path],
    result: BatchCheckResult,
    cross_album: CrossAlbumCheckResult,
    refresh_failures: tuple[BatchFailure, ...],
    flags: _CheckFlags,
    *,
    cwd: Path,
) -> bool:
    """Print the summary (and retry commands); ``True`` when nothing failed."""
    summary = compute_batch_check_summary(
        albums,
        result,
        cross_album,
        refresh_failures,
    )
    console.print(
        batch_check_summary(
            summary.passed,
            len(summary.failed_albums),
            summary.warned,
        ),
    )
    if summary.failed_albums:
        err_console.print(
            investigate_commands(
                "check",
                summary.failed_albums,
                cwd,
                extra_flags=flags.retry_flags(),
            ),
        )
    return summary.success
