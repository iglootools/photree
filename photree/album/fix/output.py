"""User-facing output formatting for album fix commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import FixResult


def refresh_jpeg_summary(converted: int, copied: int, skipped: int) -> str:
    return f"Done. {converted} converted, {copied} copied, {skipped} skipped."


def refresh_browsable_summary(
    heic_copied: int,
    mov_copied: int,
    jpeg_converted: int,
    jpeg_copied: int,
    jpeg_skipped: int,
) -> str:
    jpeg_parts = ", ".join(
        [
            *([f"{jpeg_converted} converted"] if jpeg_converted else []),
            *([f"{jpeg_copied} copied"] if jpeg_copied else []),
            *([f"{jpeg_skipped} skipped"] if jpeg_skipped else []),
        ]
    )
    parts = ", ".join(
        [
            *([f"{heic_copied} heic"] if heic_copied else []),
            *([f"{mov_copied} mov"] if mov_copied else []),
            *([f"jpeg: {jpeg_parts}"] if jpeg_parts else []),
        ]
    )
    return f"Done. {parts}." if parts else "Done. nothing to do."


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
                    f"heic: {heic_jpeg} jpeg, {heic_browsable} main, "
                    f"{heic_rendered} edit, {heic_orig} orig"
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


def rm_orphan_summary(
    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    total = sum(len(files) for _, files in removed_by_dir)
    if total == 0:
        return "Done. No orphans found."
    parts = ", ".join(f"{len(files)} from {name}" for name, files in removed_by_dir)
    return f"Done. Removed {total} orphan(s): {parts}."


def format_fix_result(result: FixResult) -> list[str]:
    """Format a :class:`FixResult` into output lines."""
    lines: list[str] = []

    if result.refresh_browsable_result is not None:
        rc = result.refresh_browsable_result
        lines.append(
            refresh_browsable_summary(
                heic_copied=rc.heic_copied,
                mov_copied=rc.mov_copied,
                jpeg_converted=rc.jpeg_converted,
                jpeg_copied=rc.jpeg_copied,
                jpeg_skipped=rc.jpeg_skipped,
            )
        )

    if result.refresh_jpeg_result is not None:
        rj = result.refresh_jpeg_result
        lines.append(refresh_jpeg_summary(rj.converted, rj.copied, rj.skipped))

    if result.rm_upstream_result is not None:
        ru = result.rm_upstream_result
        lines.append(
            rm_upstream_summary(
                heic_jpeg=ru.heic_jpeg,
                heic_browsable=ru.heic_browsable,
                heic_rendered=ru.heic_rendered,
                heic_orig=ru.heic_orig,
                mov_rendered=ru.mov_rendered,
                mov_orig=ru.mov_orig,
            )
        )

    if result.rm_orphan_removed_by_dir:
        lines.append(rm_orphan_summary(result.rm_orphan_removed_by_dir))

    return lines


def batch_fix_summary(fixed: int, failed: int) -> str:
    return f"\nDone. {fixed} album(s) fixed, {failed} failed."
