"""User-facing output formatting for album fix commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .rm_upstream import RmUpstreamSkip, SignalSkipReason

if TYPE_CHECKING:
    from . import FixResult, FixRmUpstreamResult


def rm_upstream_summary(
    heic_jpeg: int,
    heic_browsable: int,
    heic_rendered: int,
    heic_orig: int,
    mov_rendered: int,
    mov_orig: int,
) -> str:
    parts = ", ".join(
        [
            *(
                [
                    (
                        f"heic: {heic_jpeg} jpeg, {heic_browsable} main, "
                        f"{heic_rendered} edit, {heic_orig} orig"
                    )
                ]
                if heic_jpeg or heic_browsable or heic_rendered or heic_orig
                else []
            ),
            *(
                [f"mov: {mov_rendered} edit, {mov_orig} orig"]
                if mov_rendered or mov_orig
                else []
            ),
        ]
    )
    if parts:
        return f"Done. Removed {parts}."
    else:
        return "Done. Nothing to remove."


def rm_upstream_skip_line(skip: RmUpstreamSkip) -> str:
    """Explain why a browsable directory was not used as a deletion signal."""
    match skip.reason:
        case SignalSkipReason.MISSING:
            why = "directory is missing"
        case SignalSkipReason.NO_EXPECTED_FILES:
            why = "directory holds none of its expected files (use --force if intended)"
    return f"Skipped {skip.directory} as a deletion signal: {why}."


def rm_orphan_summary(
    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    total = sum(len(files) for _, files in removed_by_dir)
    if total == 0:
        return "Done. No orphans found."
    parts = ", ".join(f"{len(files)} from {name}" for name, files in removed_by_dir)
    return f"Done. Removed {total} orphan(s): {parts}."


def _rm_upstream_lines(ru: FixRmUpstreamResult) -> list[str]:
    return [
        *(rm_upstream_skip_line(skip) for skip in ru.skipped),
        rm_upstream_summary(
            heic_jpeg=ru.heic_jpeg,
            heic_browsable=ru.heic_browsable,
            heic_rendered=ru.heic_rendered,
            heic_orig=ru.heic_orig,
            mov_rendered=ru.mov_rendered,
            mov_orig=ru.mov_orig,
        ),
    ]


def format_fix_result(result: FixResult) -> list[str]:
    """Format a :class:`FixResult` into output lines."""
    return [
        *(
            ["No media sources found; nothing to fix."]
            if result.no_media_sources
            else []
        ),
        *(
            _rm_upstream_lines(result.rm_upstream_result)
            if result.rm_upstream_result is not None
            else []
        ),
        *(
            [rm_orphan_summary(result.rm_orphan_removed_by_dir)]
            if result.rm_orphan_removed_by_dir is not None
            else []
        ),
    ]


def batch_fix_summary(fixed: int, failed: int) -> str:
    return f"\nDone. {fixed} album(s) fixed, {failed} failed."
