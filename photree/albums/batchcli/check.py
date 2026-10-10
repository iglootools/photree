"""``albums check`` / ``gallery check`` wrapper."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import typer
from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...album import naming as album_naming
from ...album.check import output as preflight_output
from ...album.check.output import batch_check_summary
from ...album.exif_cache.refresh import refresh_exif_cache as _refresh_exif
from ...album.id import format_album_external_id, format_image_external_id
from ...album.naming import BatchNamingResult
from ...clihelpers.console import console, err_console
from ...clihelpers.progress import BatchProgressBar, run_with_spinner
from ...clihelpers.sysdeps import CHECK_DEPS, EXIF_DEPS, require_system_deps
from ...common.exif import exiftool_session
from ...foundation.gallery_metadata import resolve_link_mode
from ..cmd_handler import BatchFailure, failures_of, run_album_step
from ..cmd_handler.check import BatchCheckResult, batch_check
from ..index import find_duplicate_album_ids
from ..media_index import find_duplicate_media_ids
from .failures import batch_failures_report, investigate_commands
from .resolution import make_display_fn


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
        return preflight_output.batch_check_retry_flags(
            fatal_warnings=self.fatal_warnings,
            fatal_sidecar=self.fatal_sidecar_arg,
            fatal_exif_date_match=self.fatal_exif_date_match,
        )


@dataclass(frozen=True)
class _CrossAlbumResult:
    naming_result: BatchNamingResult | None
    duplicate_ids: Mapping[str, tuple[Path, ...]]
    duplicate_media_ids: Mapping[str, tuple[Path, ...]]
    failed_albums: frozenset[Path]


def _conclude(success: bool, *, exit_on_failure: bool) -> bool:
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
) -> bool:
    """Shared implementation for gallery check / albums check.

    Returns ``True`` when every album passed (or there were none). With
    ``exit_on_failure`` (the default) a failed run raises ``typer.Exit(1)``
    and an empty one ``typer.Exit(0)``; pass ``False`` to get the verdict
    back and keep going (``gallery check`` then checks collections too). A
    missing ``sips`` always exits: it is a property of the machine.
    """
    cwd = Path.cwd()
    flags = _CheckFlags(
        checksum,
        fatal_warnings,
        fatal_sidecar_arg,
        fatal_exif_date_match,
        check_naming,
        check_date_part_collision,
    )
    # --refresh-exif-cache cannot degrade without exiftool, so it is required.
    require_system_deps((*CHECK_DEPS, *EXIF_DEPS) if refresh_exif_cache else CHECK_DEPS)
    checked = _run_per_album_checks(
        albums,
        display_base,
        flags,
        cwd,
        check_exif_date_match=check_exif_date_match,
        refresh_exif_cache=refresh_exif_cache,
    )
    if checked is None:
        typer.echo("\nNo albums found.")
        if exit_on_failure:
            raise typer.Exit(code=0)
        return True
    result, refresh_failures = checked

    cross_album = run_with_spinner(
        "Running cross-album checks...",
        lambda: _compute_cross_album_checks(albums, flags),
    )
    _print_cross_album(cross_album, cwd)
    success = _report(albums, result, cross_album, refresh_failures, flags, cwd)
    return _conclude(success, exit_on_failure=exit_on_failure)


def _run_per_album_checks(
    albums: list[Path],
    display_base: Path | None,
    flags: _CheckFlags,
    cwd: Path,
    *,
    check_exif_date_match: bool,
    refresh_exif_cache: bool,
) -> tuple[BatchCheckResult, tuple[BatchFailure, ...]] | None:
    """Optionally refresh EXIF caches, then check each album.

    Returns ``None`` when there are no albums. The exiftool process lives
    exactly as long as this call, so no exit path can leak it.
    """
    with exiftool_session(enabled=check_exif_date_match or refresh_exif_cache) as et:
        if not refresh_exif_cache:
            console.print(preflight_output.exiftool_check(et is not None))
        if not albums:
            return None
        refresh_failures = (
            _refresh_exif_caches(albums, et, cwd) if refresh_exif_cache else ()
        )
        typer.echo(f"\nFound {len(albums)} album(s).\n" if display_base else "")
        return _check_albums(albums, display_base, flags, et, cwd), refresh_failures


def _refresh_exif_caches(
    albums: list[Path], exiftool: ExifToolHelper | None, cwd: Path
) -> tuple[BatchFailure, ...]:
    """Refresh every album's EXIF cache; a failing album is reported, not fatal."""
    typer.echo("\nRefreshing EXIF cache...")
    failures = failures_of(
        run_album_step(
            album_dir,
            partial(_refresh_exif, album_dir, exiftool=exiftool),
            name=album_dir.name,
        )
        for album_dir in albums
    )
    if failures:
        err_console.print(batch_failures_report(failures, cwd))
    return failures


def _check_albums(
    albums: list[Path],
    display_base: Path | None,
    flags: _CheckFlags,
    exiftool: ExifToolHelper | None,
    cwd: Path,
) -> BatchCheckResult:
    with BatchProgressBar(
        total=len(albums), description="Checking", done_description="check"
    ) as progress:
        return batch_check(
            albums,
            # require_system_deps exited already if sips were missing.
            sips_available=True,
            exiftool=exiftool,
            link_mode=resolve_link_mode(None, albums[0]),
            checksum=flags.checksum,
            fatal_sidecar=flags.fatal_sidecar,
            fatal_exif=flags.fatal_exif,
            check_naming=flags.check_naming,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success, errors, warnings: progress.on_end(
                name,
                success=success,
                error_labels=errors,
                warning_labels=warnings,
            ),
        )


def _print_cross_album(cross_album: _CrossAlbumResult, cwd: Path) -> None:
    typer.echo("\nCross-album checks:")
    if cross_album.naming_result is not None:
        console.print(
            preflight_output.format_batch_naming_issues(cross_album.naming_result)
        )
    for kind, duplicates, format_id in (
        ("album", cross_album.duplicate_ids, format_album_external_id),
        ("media", cross_album.duplicate_media_ids, format_image_external_id),
    ):
        if duplicates:
            err_console.print(
                preflight_output.duplicate_ids_report(
                    kind, {k: list(v) for k, v in duplicates.items()}, cwd, format_id
                )
            )
        else:
            console.print(preflight_output.no_duplicate_ids_line(kind))


def _report(
    albums: list[Path],
    result: BatchCheckResult,
    cross_album: _CrossAlbumResult,
    refresh_failures: tuple[BatchFailure, ...],
    flags: _CheckFlags,
    cwd: Path,
) -> bool:
    """Print the summary (and retry commands); ``True`` when nothing failed."""
    # An album can fail several ways (refresh, per-album, cross-album checks):
    # it is counted once, and ``passed`` is whatever did not fail.
    failed = frozenset(
        {
            *result.failed_albums,
            *cross_album.failed_albums,
            *(f.album_dir for f in refresh_failures),
        }
    )
    warned = len(set(result.warned_albums) - failed)
    console.print(batch_check_summary(len(albums) - len(failed), len(failed), warned))
    if failed:
        err_console.print(
            investigate_commands(
                "check", sorted(failed), cwd, extra_flags=flags.retry_flags()
            )
        )
    return not failed


def _date_collision_check(
    albums: list[Path], flags: _CheckFlags
) -> tuple[BatchNamingResult | None, frozenset[Path]]:
    if not (flags.check_naming and flags.check_date_part_collision):
        return None, frozenset()
    naming_result = album_naming.check_batch_date_collisions(
        [
            (album.name, parsed)
            for album in albums
            if (parsed := album_naming.parse_album_name(album.name)) is not None
        ]
    )
    colliding = {name for _, names in naming_result.date_collisions for name in names}
    return naming_result, frozenset(a for a in albums if a.name in colliding)


def _compute_cross_album_checks(
    albums: list[Path], flags: _CheckFlags
) -> _CrossAlbumResult:
    """Run cross-album checks (date collisions, duplicate IDs)."""
    naming_result, colliding = _date_collision_check(albums, flags)
    duplicate_ids = {k: tuple(v) for k, v in find_duplicate_album_ids(albums).items()}
    duplicate_media_ids = {
        k: tuple(v) for k, v in find_duplicate_media_ids(albums).items()
    }
    return _CrossAlbumResult(
        naming_result=naming_result,
        duplicate_ids=duplicate_ids,
        duplicate_media_ids=duplicate_media_ids,
        failed_albums=frozenset(
            {
                *colliding,
                *(p for paths in duplicate_ids.values() for p in paths),
                *(p for paths in duplicate_media_ids.values() for p in paths),
            }
        ),
    )
