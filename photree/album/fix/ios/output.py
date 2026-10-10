"""User-facing output formatting for iOS fix commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .miscategorized import MiscategorizedAction

if TYPE_CHECKING:
    from . import FixIosMiscategorizedResult, FixIosResult


def rm_orphan_sidecar_summary(
    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    total = sum(len(files) for _, files in removed_by_dir)
    if total == 0:
        return "Done. No orphan sidecars found."
    parts = ", ".join(f"{len(files)} from {name}" for name, files in removed_by_dir)
    return f"Done. Removed {total} orphan sidecar(s): {parts}."


def prefer_higher_quality_summary(
    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    total = sum(len(files) for _, files in removed_by_dir)
    if total == 0:
        return "Done. No duplicates found."
    parts = ", ".join(f"{len(files)} from {name}" for name, files in removed_by_dir)
    return f"Done. Removed {total} lower-quality duplicate(s): {parts}."


def miscategorized_summary(
    action: MiscategorizedAction,
    heic_from_orig: int,
    heic_from_rendered: int,
    mov_from_orig: int,
    mov_from_rendered: int,
) -> str:
    total = heic_from_orig + heic_from_rendered + mov_from_orig + mov_from_rendered
    if total == 0:
        return "Done. No miscategorized files found."
    verb = "Moved" if action == MiscategorizedAction.MV else "Removed"
    parts = ", ".join(
        [
            *(
                [f"{heic_from_orig} edited file(s) from orig-img"]
                if heic_from_orig
                else []
            ),
            *(
                [f"{heic_from_rendered} original file(s) from edit-img"]
                if heic_from_rendered
                else []
            ),
            *(
                [f"{mov_from_orig} edited file(s) from orig-vid"]
                if mov_from_orig
                else []
            ),
            *(
                [f"{mov_from_rendered} original file(s) from edit-vid"]
                if mov_from_rendered
                else []
            ),
        ]
    )
    return f"Done. {verb} {total} miscategorized file(s): {parts}."


def _miscategorized_line(mc: FixIosMiscategorizedResult) -> str:
    return miscategorized_summary(
        action=mc.action,
        heic_from_orig=mc.heic_from_orig,
        heic_from_rendered=mc.heic_from_rendered,
        mov_from_orig=mc.mov_from_orig,
        mov_from_rendered=mc.mov_from_rendered,
    )


def format_fix_ios_result(result: FixIosResult) -> list[str]:
    """Format a :class:`FixIosResult` into output lines.

    Every requested operation produces a line, including "nothing found".
    """
    sidecars = result.rm_orphan_sidecar_removed_by_dir
    dups = result.prefer_higher_quality_removed_by_dir
    miscategorized = result.miscategorized_result
    return [
        *(
            ["No iOS media sources found; nothing to fix."]
            if result.no_ios_media_sources
            else []
        ),
        *([rm_orphan_sidecar_summary(sidecars)] if sidecars is not None else []),
        *([prefer_higher_quality_summary(dups)] if dups is not None else []),
        *([_miscategorized_line(miscategorized)] if miscategorized is not None else []),
    ]


def batch_fix_ios_summary(fixed: int, failed: int) -> str:
    return f"\nDone. {fixed} album(s) fixed, {failed} failed."
