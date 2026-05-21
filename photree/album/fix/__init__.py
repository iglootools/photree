"""Generic fix operations for all album media source types.

Unlike :mod:`fix.ios` which requires iOS media sources, these operations
work with both iOS and std media sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...fsprotocol import LinkMode
from .rm_orphan import RmOrphanDirResult, RmOrphanResult, rm_orphan
from .rm_upstream import (
    RmUpstreamHeicResult,
    RmUpstreamMovResult,
    RmUpstreamResult,
    rm_upstream,
)

__all__ = [
    "FixResult",
    "FixRmUpstreamResult",
    "FixValidationError",
    "RmOrphanDirResult",
    "RmOrphanResult",
    "RmUpstreamHeicResult",
    "RmUpstreamMovResult",
    "RmUpstreamResult",
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
    rm_upstream: bool,
    rm_orphan: bool,
) -> None:
    """Validate fix flag combinations.

    Raises :class:`FixValidationError` when no fix is specified.
    """
    any_fix = fix_id or new_id or rm_upstream or rm_orphan
    if not any_fix:
        raise FixValidationError(
            "No fix specified. Run photree album fix --help for available fixes."
        )


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

    rm_upstream_result: FixRmUpstreamResult | None = None
    rm_orphan_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()


def run_fix(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    rm_upstream_flag: bool = False,
    rm_orphan_flag: bool = False,
    max_workers: int | None = None,
) -> FixResult:
    """Run selected fix operations on a single album.

    Iterates over all media sources with archives, runs the requested
    operations, and returns aggregated results. Works for both iOS and
    std media sources.
    """
    from ..store.media_sources_discovery import discover_media_sources

    # Include media sources that have an archive dir on disk
    media_sources = [
        ms
        for ms in discover_media_sources(album_dir)
        if (album_dir / ms.archive_dir).is_dir()
    ]

    if not media_sources:
        return FixResult()

    ru_result = None
    orphan_by_dir: list[tuple[str, tuple[str, ...]]] = []

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
        rm_upstream_result=ru_result,
        rm_orphan_removed_by_dir=tuple(orphan_by_dir),
    )
