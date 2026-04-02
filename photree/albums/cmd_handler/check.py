"""Batch check command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...album import (
    check as album_preflight,
    naming as album_naming,
)
from ...album.naming import BatchNamingResult
from ...album.store.protocol import format_album_external_id
from ..index import find_duplicate_album_ids


@dataclass(frozen=True)
class BatchCheckResult:
    """Result of batch album checking."""

    passed: int
    warned: int
    failed_albums: list[Path] = field(default_factory=list)
    naming_result: BatchNamingResult | None = None
    duplicate_ids: dict[str, list[Path]] = field(default_factory=dict)


def batch_check(
    albums: list[Path],
    *,
    sips_available: bool,
    exiftool: ExifToolHelper | None = None,
    checksum: bool = True,
    fatal_warnings: bool = False,
    fatal_sidecar: bool = False,
    fatal_exif: bool = True,
    check_naming: bool = True,
    check_date_part_collision: bool = True,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...], tuple[str, ...]], None] | None = None,
) -> BatchCheckResult:
    """Check multiple albums and return aggregated results.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels, warning_labels)`` after each album.

    The caller is responsible for managing the exiftool process lifecycle.
    """
    passed = 0
    warned = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = display_fn(album_dir)

        if on_start:
            on_start(album_name)

        result = album_preflight.run_album_check(
            album_dir,
            sips_available=sips_available,
            exiftool=exiftool,
            checksum=checksum,
            check_naming_flag=check_naming,
        )

        # Include external album ID in the label when available
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
            if on_end:
                on_end(album_label, True, (), warn_labels)
            passed += 1
            if result.has_warnings:
                warned += 1
        else:
            if on_end:
                on_end(album_label, False, err_labels, warn_labels)
            failed_albums.append(album_dir)

    # Batch naming checks (date collisions across all albums)
    naming_result = None
    if check_naming and check_date_part_collision:
        parsed_albums = [
            (album.name, parsed)
            for album in albums
            if (parsed := album_naming.parse_album_name(album.name)) is not None
        ]
        naming_result = album_naming.check_batch_date_collisions(parsed_albums)
        if not naming_result.success:
            colliding_names = {
                name for _, names in naming_result.date_collisions for name in names
            }
            failed_albums.extend(a for a in albums if a.name in colliding_names)

    # Duplicate album ID detection
    duplicate_ids = find_duplicate_album_ids(albums)
    if duplicate_ids:
        failed_albums.extend(p for paths in duplicate_ids.values() for p in paths)

    return BatchCheckResult(
        passed=passed,
        warned=warned,
        failed_albums=failed_albums,
        naming_result=naming_result,
        duplicate_ids=duplicate_ids,
    )
