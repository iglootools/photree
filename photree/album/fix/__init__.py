"""
Generic fix operations for all album media source types.

Unlike :mod:`fix.ios` which requires iOS media sources, these operations
work with both iOS and std media sources.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.fix.helpers import MissingArchiveError
from photree.album.fix.rm_orphan import RmOrphanDirResult, RmOrphanResult, rm_orphan
from photree.album.fix.rm_upstream import (
    RmUpstreamHeicResult,
    RmUpstreamMovResult,
    RmUpstreamRefusedError,
    RmUpstreamResult,
    RmUpstreamSkip,
    SignalSkipReason,
    rm_upstream,
)
from photree.album.store.media_source import MediaSource
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.foundation.linking import LinkMode

__all__ = [
    "FixResult",
    "FixRmUpstreamResult",
    "FixValidationError",
    "FixValidationErrorKind",
    "LinkMode",
    "MissingArchiveError",
    "RmOrphanDirResult",
    "RmOrphanResult",
    "RmUpstreamHeicResult",
    "RmUpstreamMovResult",
    "RmUpstreamRefusedError",
    "RmUpstreamResult",
    "RmUpstreamSkip",
    "SignalSkipReason",
    "rm_orphan",
    "rm_upstream",
    "run_fix",
    "validate_fix_flags",
]


class FixValidationErrorKind(StrEnum):
    """Why the requested fix options are invalid."""

    NO_FIX_SPECIFIED = "no-fix-specified"


class FixValidationError(ValueError):
    """
    No fix was requested.

    The message carries no command advice: each CLI scope (album, albums,
    gallery) suggests its own ``--help``.
    """

    def __init__(self, kind: FixValidationErrorKind) -> None:
        """Build the error from its *kind*."""
        self.kind = kind
        super().__init__("No fix specified.")


def validate_fix_flags(
    *,
    fix_id: bool = False,
    new_id: bool = False,
    rm_upstream: bool,
    rm_orphan: bool,
) -> None:
    """Raise :class:`FixValidationError` when no fix is specified."""
    if not (fix_id or new_id or rm_upstream or rm_orphan):
        raise FixValidationError(FixValidationErrorKind.NO_FIX_SPECIFIED)


@dataclass(frozen=True)
class FixRmUpstreamResult:
    """The number of files rm-upstream removed per directory, summed over sources."""

    heic_jpeg: int
    heic_browsable: int
    heic_rendered: int
    heic_orig: int
    mov_rendered: int
    mov_orig: int
    skipped: tuple[RmUpstreamSkip, ...] = ()

    @staticmethod
    def from_results(results: Sequence[RmUpstreamResult]) -> FixRmUpstreamResult:
        """Sum the per-media-source *results* and collect every skipped signal."""
        return FixRmUpstreamResult(
            heic_jpeg=sum(len(r.heic.removed_jpeg) for r in results),
            heic_browsable=sum(len(r.heic.removed_browsable) for r in results),
            heic_rendered=sum(len(r.heic.removed_rendered) for r in results),
            heic_orig=sum(len(r.heic.removed_orig) for r in results),
            mov_rendered=sum(len(r.mov.removed_rendered) for r in results),
            mov_orig=sum(len(r.mov.removed_orig) for r in results),
            skipped=tuple(skip for r in results for skip in r.skipped),
        )


@dataclass(frozen=True)
class FixResult:
    """
    The outcome of each fix operation.

    ``None`` means the operation was not requested; an empty value means it
    ran and found nothing, which is reported as such.
    """

    rm_upstream_result: FixRmUpstreamResult | None = None
    rm_orphan_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] | None = None
    no_media_sources: bool = False


def _run_rm_orphan(
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    dry_run: bool,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        entry
        for ms in media_sources
        for result in [rm_orphan(album_dir, ms, dry_run=dry_run)]
        for entry in (*result.heic.removed_by_dir, *result.mov.removed_by_dir)
    )


def run_fix(
    album_dir: Path,
    *,
    dry_run: bool,
    rm_upstream_flag: bool = False,
    rm_orphan_flag: bool = False,
    force: bool = False,
) -> FixResult:
    """
    Run the requested fixes on one album.

    *force* lets rm-upstream use empty browsable dirs as deletion signals and
    delete every item of an archive (see :mod:`photree.album.fix.rm_upstream`).
    """
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        return FixResult(no_media_sources=True)

    return FixResult(
        rm_upstream_result=(
            FixRmUpstreamResult.from_results(
                rm_upstream(album_dir, media_sources, dry_run=dry_run, force=force),
            )
            if rm_upstream_flag
            else None
        ),
        rm_orphan_removed_by_dir=(
            _run_rm_orphan(album_dir, media_sources, dry_run=dry_run)
            if rm_orphan_flag
            else None
        ),
    )
