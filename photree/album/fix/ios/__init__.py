"""Fix operations for iOS albums.

Each function orchestrates a specific fix: deleting stale data, rebuilding
from sources, and returning a structured result. CLI concerns (progress bars,
output formatting, exit codes) are handled by the caller.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...store.media_source import MediaSource
from ...store.media_sources_discovery import discover_media_sources
from .miscategorized import (
    MiscategorizedAction,
    MiscategorizedDirResult,
    MiscategorizedMoveConflictError,
    MiscategorizedResult,
    fix_miscategorized,
    mv_miscategorized,
    rm_miscategorized,
    rm_miscategorized_safe,
)
from .prefer_higher_quality import (
    PreferHigherQualityResult,
    prefer_higher_quality_when_dups,
)
from .rm_orphan_sidecar import RmOrphanSidecarResult, rm_orphan_sidecar

__all__ = [
    "FixIosMiscategorizedResult",
    "FixIosResult",
    "FixIosValidationError",
    "FixIosValidationErrorKind",
    "MiscategorizedAction",
    "MiscategorizedDirResult",
    "MiscategorizedMoveConflictError",
    "MiscategorizedResult",
    "PreferHigherQualityResult",
    "RmOrphanSidecarResult",
    "mv_miscategorized",
    "prefer_higher_quality_when_dups",
    "rm_miscategorized",
    "rm_miscategorized_safe",
    "rm_orphan_sidecar",
    "run_fix_ios",
    "validate_fix_flags",
]


# ---------------------------------------------------------------------------
# Flag validation
# ---------------------------------------------------------------------------


class FixIosValidationErrorKind(StrEnum):
    MUTUALLY_EXCLUSIVE = "mutually-exclusive"
    NO_FIX_SPECIFIED = "no-fix-specified"


_MISCATEGORIZED_FLAGS = (
    "--rm-miscategorized",
    "--rm-miscategorized-safe",
    "--mv-miscategorized",
)


class FixIosValidationError(ValueError):
    """Raised when fix-ios flag combinations are invalid.

    ``flags`` lists the offending options (for ``MUTUALLY_EXCLUSIVE``). The
    message carries no command advice: each CLI scope suggests its own help.
    """

    def __init__(
        self, kind: FixIosValidationErrorKind, flags: tuple[str, ...] = ()
    ) -> None:
        self.kind = kind
        self.flags = flags
        super().__init__(
            f"{', '.join(flags)} are mutually exclusive."
            if kind == FixIosValidationErrorKind.MUTUALLY_EXCLUSIVE
            else "No fix specified."
        )


def _miscategorized_action(
    *, rm: bool, rm_safe: bool, mv: bool
) -> MiscategorizedAction | None:
    """Map the three mutually exclusive flags to an action (validated first)."""
    match (rm, rm_safe, mv):
        case (True, False, False):
            return MiscategorizedAction.RM
        case (False, True, False):
            return MiscategorizedAction.RM_SAFE
        case (False, False, True):
            return MiscategorizedAction.MV
        case (False, False, False):
            return None
        case _:
            raise FixIosValidationError(
                FixIosValidationErrorKind.MUTUALLY_EXCLUSIVE,
                tuple(
                    flag
                    for flag, on in zip(_MISCATEGORIZED_FLAGS, (rm, rm_safe, mv))
                    if on
                ),
            )


def validate_fix_flags(
    *,
    rm_orphan_sidecar: bool,
    prefer_higher_quality_when_dups: bool,
    rm_miscategorized: bool,
    rm_miscategorized_safe: bool,
    mv_miscategorized: bool,
) -> None:
    """Validate fix-ios flag combinations.

    Raises :class:`FixIosValidationError` on invalid combinations.
    """
    action = _miscategorized_action(
        rm=rm_miscategorized, rm_safe=rm_miscategorized_safe, mv=mv_miscategorized
    )
    if not (rm_orphan_sidecar or prefer_higher_quality_when_dups or action):
        raise FixIosValidationError(FixIosValidationErrorKind.NO_FIX_SPECIFIED)


# ---------------------------------------------------------------------------
# Aggregated fix-ios runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixIosMiscategorizedResult:
    """Aggregated result of miscategorized fix across media sources."""

    action: MiscategorizedAction
    heic_from_orig: int
    heic_from_rendered: int
    mov_from_orig: int
    mov_from_rendered: int


@dataclass(frozen=True)
class FixIosResult:
    """Aggregated result of all fix-ios operations on a single album.

    ``None`` means the operation was not requested; an empty value means it
    ran and found nothing, which is reported as such.
    """

    rm_orphan_sidecar_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] | None = (
        None
    )
    prefer_higher_quality_removed_by_dir: (
        tuple[tuple[str, tuple[str, ...]], ...] | None
    ) = None
    miscategorized_result: FixIosMiscategorizedResult | None = None
    no_ios_media_sources: bool = False


def _run_miscategorized(
    album_dir: Path,
    media_sources: list[MediaSource],
    action: MiscategorizedAction,
    *,
    dry_run: bool,
) -> FixIosMiscategorizedResult:
    results = [
        fix_miscategorized(album_dir, ms, action=action, dry_run=dry_run)
        for ms in media_sources
    ]
    return FixIosMiscategorizedResult(
        action=action,
        heic_from_orig=sum(len(r.heic.fixed_from_orig) for r in results),
        heic_from_rendered=sum(len(r.heic.fixed_from_rendered) for r in results),
        mov_from_orig=sum(len(r.mov.fixed_from_orig) for r in results),
        mov_from_rendered=sum(len(r.mov.fixed_from_rendered) for r in results),
    )


# Aliases for use within run_fix_ios where parameter names shadow module functions
_rm_orphan_sidecar = rm_orphan_sidecar
_prefer_higher_quality = prefer_higher_quality_when_dups


def _removed_by_dir(
    fix: Callable[..., PreferHigherQualityResult | RmOrphanSidecarResult],
    album_dir: Path,
    media_sources: list[MediaSource],
    *,
    dry_run: bool,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Run a per-source removal fix on every source and concatenate the results."""
    return tuple(
        entry
        for ms in media_sources
        for entry in fix(album_dir, ms, dry_run=dry_run).removed_by_dir
    )


def run_fix_ios(
    album_dir: Path,
    *,
    dry_run: bool,
    rm_orphan_sidecar: bool = False,
    prefer_higher_quality_when_dups: bool = False,
    rm_miscategorized: bool = False,
    rm_miscategorized_safe: bool = False,
    mv_miscategorized: bool = False,
) -> FixIosResult:
    """Run selected fix-ios operations on a single album.

    Iterates over all iOS media sources, runs the requested operations,
    and returns aggregated results. An album without iOS media sources is
    reported through ``no_ios_media_sources`` rather than an empty result.
    """
    media_sources = [ms for ms in discover_media_sources(album_dir) if ms.is_ios]
    if not media_sources:
        return FixIosResult(no_ios_media_sources=True)

    action = _miscategorized_action(
        rm=rm_miscategorized, rm_safe=rm_miscategorized_safe, mv=mv_miscategorized
    )
    return FixIosResult(
        rm_orphan_sidecar_removed_by_dir=(
            _removed_by_dir(
                _rm_orphan_sidecar, album_dir, media_sources, dry_run=dry_run
            )
            if rm_orphan_sidecar
            else None
        ),
        prefer_higher_quality_removed_by_dir=(
            _removed_by_dir(
                _prefer_higher_quality, album_dir, media_sources, dry_run=dry_run
            )
            if prefer_higher_quality_when_dups
            else None
        ),
        miscategorized_result=(
            _run_miscategorized(album_dir, media_sources, action, dry_run=dry_run)
            if action is not None
            else None
        ),
    )
