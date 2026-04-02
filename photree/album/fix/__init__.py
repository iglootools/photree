"""Generic fix operations for all album media source types.

Unlike :mod:`fix.ios` which requires iOS media sources, these operations
work with both iOS and std media sources.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...fs import LinkMode

from .refresh_jpeg import refresh_jpeg
from .refresh_browsable import RefreshBrowsableResult, refresh_browsable
from .rm_orphan import RmOrphanDirResult, RmOrphanResult, rm_orphan
from .rm_upstream import (
    RmUpstreamHeicResult,
    RmUpstreamMovResult,
    RmUpstreamResult,
    rm_upstream,
)

__all__ = [
    "FixRefreshBrowsableResult",
    "FixRefreshJpegResult",
    "FixResult",
    "FixRmUpstreamResult",
    "FixValidationError",
    "RefreshBrowsableResult",
    "RmOrphanDirResult",
    "RmOrphanResult",
    "RmUpstreamHeicResult",
    "RmUpstreamMovResult",
    "RmUpstreamResult",
    "refresh_browsable",
    "refresh_jpeg",
    "rm_orphan",
    "rm_upstream",
    "run_fix",
    "validate_fix_flags",
]


# ---------------------------------------------------------------------------
# Aggregated fix runner
# ---------------------------------------------------------------------------


class FixValidationError(ValueError):
    """Raised when fix flag combinations are invalid."""


def validate_fix_flags(
    *,
    fix_id: bool = False,
    new_id: bool = False,
    refresh_browsable: bool,
    refresh_jpeg: bool,
    rm_upstream: bool,
    rm_orphan: bool,
) -> None:
    """Validate fix flag combinations.

    Raises :class:`FixValidationError` when no fix is specified.
    """
    any_fix = (
        fix_id
        or new_id
        or refresh_browsable
        or refresh_jpeg
        or rm_upstream
        or rm_orphan
    )
    if not any_fix:
        raise FixValidationError(
            "No fix specified. Run photree album fix --help for available fixes."
        )


@dataclass(frozen=True)
class FixRefreshBrowsableResult:
    """Aggregated result of refresh-browsable across media sources."""

    heic_copied: int
    mov_copied: int
    jpeg_converted: int
    jpeg_copied: int
    jpeg_skipped: int


@dataclass(frozen=True)
class FixRefreshJpegResult:
    """Aggregated result of refresh-jpeg across media sources."""

    converted: int
    copied: int
    skipped: int


@dataclass(frozen=True)
class FixRmUpstreamResult:
    """Aggregated result of rm-upstream across media sources."""

    heic_jpeg: int
    heic_browsable: int
    heic_rendered: int
    heic_orig: int
    mov_rendered: int
    mov_orig: int


@dataclass(frozen=True)
class FixResult:
    """Aggregated result of all fix operations on a single album."""

    refresh_browsable_result: FixRefreshBrowsableResult | None = None
    refresh_jpeg_result: FixRefreshJpegResult | None = None
    rm_upstream_result: FixRmUpstreamResult | None = None
    rm_orphan_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()


def run_fix(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    refresh_browsable_flag: bool = False,
    refresh_jpeg_flag: bool = False,
    rm_upstream_flag: bool = False,
    rm_orphan_flag: bool = False,
    on_refresh_browsable_stage_start: Callable[[str], None] | None = None,
    on_refresh_browsable_stage_end: Callable[[str], None] | None = None,
    on_refresh_jpeg_file_start: Callable[[str], None] | None = None,
    on_refresh_jpeg_file_end: Callable[[str, bool], None] | None = None,
) -> FixResult:
    """Run selected fix operations on a single album.

    Iterates over all media sources with archives, runs the requested
    operations, and returns aggregated results. Works for both iOS and
    std media sources.
    """
    from ...fs import discover_media_sources

    # Include media sources that have an archive dir on disk
    media_sources = [
        ms
        for ms in discover_media_sources(album_dir)
        if ms.is_ios or (album_dir / ms.archive_dir).is_dir()
    ]

    if not media_sources:
        return FixResult()

    rc_result = None
    rj_result = None
    ru_result = None
    orphan_by_dir: list[tuple[str, tuple[str, ...]]] = []

    if refresh_browsable_flag:
        total_heic = 0
        total_mov = 0
        total_jpeg_converted = 0
        total_jpeg_copied = 0
        total_jpeg_skipped = 0
        for ms in media_sources:
            result = refresh_browsable(
                album_dir,
                ms,
                link_mode=link_mode,
                dry_run=dry_run,
                on_stage_start=on_refresh_browsable_stage_start,
                on_stage_end=on_refresh_browsable_stage_end,
            )
            total_heic += result.heic.copied
            total_mov += result.mov.copied
            total_jpeg_converted += result.jpeg.converted if result.jpeg else 0
            total_jpeg_copied += result.jpeg.copied if result.jpeg else 0
            total_jpeg_skipped += result.jpeg.skipped if result.jpeg else 0
        rc_result = FixRefreshBrowsableResult(
            heic_copied=total_heic,
            mov_copied=total_mov,
            jpeg_converted=total_jpeg_converted,
            jpeg_copied=total_jpeg_copied,
            jpeg_skipped=total_jpeg_skipped,
        )
    elif refresh_jpeg_flag:
        total_converted = 0
        total_copied = 0
        total_skipped = 0
        for ms in media_sources:
            if not (album_dir / ms.img_dir).is_dir():
                continue
            result_jpeg = refresh_jpeg(
                album_dir,
                ms,
                dry_run=dry_run,
                on_file_start=on_refresh_jpeg_file_start,
                on_file_end=on_refresh_jpeg_file_end,
            )
            total_converted += result_jpeg.converted
            total_copied += result_jpeg.copied
            total_skipped += result_jpeg.skipped
        rj_result = FixRefreshJpegResult(
            converted=total_converted,
            copied=total_copied,
            skipped=total_skipped,
        )

    if rm_upstream_flag:
        total_heic_jpeg = 0
        total_heic_browsable = 0
        total_heic_rendered = 0
        total_heic_orig = 0
        total_mov_rendered = 0
        total_mov_orig = 0
        for ms in media_sources:
            result_rm = rm_upstream(album_dir, ms, dry_run=dry_run)
            total_heic_jpeg += len(result_rm.heic.removed_jpeg)
            total_heic_browsable += len(result_rm.heic.removed_browsable)
            total_heic_rendered += len(result_rm.heic.removed_rendered)
            total_heic_orig += len(result_rm.heic.removed_orig)
            total_mov_rendered += len(result_rm.mov.removed_rendered)
            total_mov_orig += len(result_rm.mov.removed_orig)
        ru_result = FixRmUpstreamResult(
            heic_jpeg=total_heic_jpeg,
            heic_browsable=total_heic_browsable,
            heic_rendered=total_heic_rendered,
            heic_orig=total_heic_orig,
            mov_rendered=total_mov_rendered,
            mov_orig=total_mov_orig,
        )

    if rm_orphan_flag:
        for ms in media_sources:
            result_orphan = rm_orphan(album_dir, ms, dry_run=dry_run)
            orphan_by_dir.extend(result_orphan.heic.removed_by_dir)
            orphan_by_dir.extend(result_orphan.mov.removed_by_dir)

    return FixResult(
        refresh_browsable_result=rc_result,
        refresh_jpeg_result=rj_result,
        rm_upstream_result=ru_result,
        rm_orphan_removed_by_dir=tuple(orphan_by_dir),
    )
