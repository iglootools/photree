"""Fix operations for iOS albums.

Each function orchestrates a specific fix: deleting stale data, rebuilding
from sources, and returning a structured result. CLI concerns (progress bars,
output formatting, exit codes) are handled by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .miscategorized import (
    MiscategorizedDirResult,
    MiscategorizedResult,
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
    "MiscategorizedDirResult",
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
# Aggregated fix-ios runner
# ---------------------------------------------------------------------------


class FixIosValidationError(ValueError):
    """Raised when fix-ios flag combinations are invalid."""


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
    miscat_flags = sum([rm_miscategorized, rm_miscategorized_safe, mv_miscategorized])
    if miscat_flags > 1:
        raise FixIosValidationError(
            "--rm-miscategorized, --rm-miscategorized-safe, and --mv-miscategorized "
            "are mutually exclusive."
        )

    any_fix = rm_orphan_sidecar or prefer_higher_quality_when_dups or miscat_flags > 0
    if not any_fix:
        raise FixIosValidationError(
            "No fix specified. Run photree album fix-ios --help for available fixes."
        )


@dataclass(frozen=True)
class FixIosMiscategorizedResult:
    """Aggregated result of miscategorized fix across media sources."""

    action: str
    heic_from_orig: int
    heic_from_rendered: int
    mov_from_orig: int
    mov_from_rendered: int


@dataclass(frozen=True)
class FixIosResult:
    """Aggregated result of all fix-ios operations on a single album."""

    rm_orphan_sidecar_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()
    prefer_higher_quality_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()
    miscategorized_result: FixIosMiscategorizedResult | None = None


# Aliases for use within run_fix_ios where parameter names shadow module functions
_do_rm_orphan_sidecar = rm_orphan_sidecar
_do_prefer_higher_quality = prefer_higher_quality_when_dups
_do_rm_miscategorized = rm_miscategorized
_do_rm_miscategorized_safe = rm_miscategorized_safe
_do_mv_miscategorized = mv_miscategorized


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
    and returns aggregated results. The caller handles output formatting
    and progress bars via the optional callbacks.
    """
    from ...store.media_sources_discovery import discover_media_sources

    media_sources = [c for c in discover_media_sources(album_dir) if c.is_ios]

    if not media_sources:
        return FixIosResult()

    orphan_sidecar_by_dir: list[tuple[str, tuple[str, ...]]] = []
    higher_quality_by_dir: list[tuple[str, tuple[str, ...]]] = []
    miscat_result = None

    if rm_orphan_sidecar:
        for ms in media_sources:
            result_meta = _do_rm_orphan_sidecar(album_dir, ms, dry_run=dry_run)
            orphan_sidecar_by_dir.extend(result_meta.removed_by_dir)

    if prefer_higher_quality_when_dups:
        for ms in media_sources:
            result_hq = _do_prefer_higher_quality(album_dir, ms, dry_run=dry_run)
            higher_quality_by_dir.extend(result_hq.removed_by_dir)

    miscat_action = (
        "rm"
        if rm_miscategorized
        else "rm-safe"
        if rm_miscategorized_safe
        else "mv"
        if mv_miscategorized
        else None
    )
    if miscat_action:
        fix_fn = {
            "rm": _do_rm_miscategorized,
            "rm-safe": _do_rm_miscategorized_safe,
            "mv": _do_mv_miscategorized,
        }[miscat_action]
        total_heic_from_orig = 0
        total_heic_from_rendered = 0
        total_mov_from_orig = 0
        total_mov_from_rendered = 0
        for ms in media_sources:
            result_miscat = fix_fn(album_dir, ms, dry_run=dry_run)
            total_heic_from_orig += len(result_miscat.heic.fixed_from_orig)
            total_heic_from_rendered += len(result_miscat.heic.fixed_from_rendered)
            total_mov_from_orig += len(result_miscat.mov.fixed_from_orig)
            total_mov_from_rendered += len(result_miscat.mov.fixed_from_rendered)
        miscat_result = FixIosMiscategorizedResult(
            action=miscat_action,
            heic_from_orig=total_heic_from_orig,
            heic_from_rendered=total_heic_from_rendered,
            mov_from_orig=total_mov_from_orig,
            mov_from_rendered=total_mov_from_rendered,
        )

    return FixIosResult(
        rm_orphan_sidecar_removed_by_dir=tuple(orphan_sidecar_by_dir),
        prefer_higher_quality_removed_by_dir=tuple(higher_quality_by_dir),
        miscategorized_result=miscat_result,
    )
