"""Batch check command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...album import (
    check as album_check,
)
from ...album.id import format_album_external_id
from ...fsprotocol import LinkMode

type OnCheckEnd = Callable[[str, bool, tuple[str, ...], tuple[str, ...]], None]


@dataclass(frozen=True)
class BatchCheckResult:
    """Result of batch album checking.

    ``failed_albums`` includes albums whose check itself crashed (their reason
    is the error label reported through ``on_end``).
    """

    passed: int
    warned: int
    failed_albums: tuple[Path, ...] = ()
    warned_albums: tuple[Path, ...] = ()  # passed, but with warnings


@dataclass(frozen=True)
class CheckOptions:
    """Per-album check settings shared by every album of a batch."""

    sips_available: bool
    exiftool: ExifToolHelper | None
    link_mode: LinkMode
    checksum: bool = True
    fatal_sidecar: bool = False
    fatal_exif: bool = True
    check_naming: bool = True


@dataclass(frozen=True)
class _AlbumOutcome:
    album_dir: Path
    ok: bool
    has_warnings: bool


def _album_label(album_name: str, result: album_check.AlbumPreflightResult) -> str:
    """Include the external album ID in the label when available."""
    id_check = result.album_id_check
    return (
        f"{album_name} ({format_album_external_id(id_check.album_id)})"
        if id_check is not None and id_check.album_id is not None
        else album_name
    )


def _check_one(
    album_dir: Path,
    album_name: str,
    opts: CheckOptions,
    on_end: OnCheckEnd | None,
) -> _AlbumOutcome:
    result = album_check.run_album_check(
        album_dir,
        sips_available=opts.sips_available,
        exiftool=opts.exiftool,
        link_mode=opts.link_mode,
        checksum=opts.checksum,
        check_naming_flag=opts.check_naming,
    )
    fatal = {"fatal_sidecar": opts.fatal_sidecar, "fatal_exif": opts.fatal_exif}
    ok = result.success and not result.has_fatal_warnings(**fatal)
    err_labels = (
        () if ok else (*result.error_labels, *result.fatal_warning_labels(**fatal))
    )
    if on_end:
        on_end(
            _album_label(album_name, result),
            ok,
            err_labels,
            result.non_fatal_warning_labels(**fatal),
        )
    return _AlbumOutcome(album_dir, ok, ok and result.has_warnings)


def _check_one_safely(
    album_dir: Path,
    album_name: str,
    opts: CheckOptions,
    on_start: Callable[[str], None] | None,
    on_end: OnCheckEnd | None,
) -> _AlbumOutcome:
    """Check one album; an album whose check crashes is a failure, not an abort."""
    if on_start:
        on_start(album_name)
    try:
        return _check_one(album_dir, album_name, opts, on_end)
    except Exception as exc:
        if on_end:
            on_end(album_name, False, (str(exc),), ())
        return _AlbumOutcome(album_dir, ok=False, has_warnings=False)


def batch_check(
    albums: list[Path],
    *,
    sips_available: bool,
    exiftool: ExifToolHelper | None = None,
    link_mode: LinkMode,
    checksum: bool = True,
    fatal_sidecar: bool = False,
    fatal_exif: bool = True,
    check_naming: bool = True,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: OnCheckEnd | None = None,
) -> BatchCheckResult:
    """Check multiple albums and return aggregated results.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels, warning_labels)`` after each album.

    The caller is responsible for managing the exiftool process lifecycle.
    """
    opts = CheckOptions(
        sips_available=sips_available,
        exiftool=exiftool,
        link_mode=link_mode,
        checksum=checksum,
        fatal_sidecar=fatal_sidecar,
        fatal_exif=fatal_exif,
        check_naming=check_naming,
    )
    outcomes = [
        _check_one_safely(album_dir, display_fn(album_dir), opts, on_start, on_end)
        for album_dir in albums
    ]
    return BatchCheckResult(
        passed=sum(1 for o in outcomes if o.ok),
        warned=sum(1 for o in outcomes if o.has_warnings),
        failed_albums=tuple(o.album_dir for o in outcomes if not o.ok),
        warned_albums=tuple(o.album_dir for o in outcomes if o.has_warnings),
    )
