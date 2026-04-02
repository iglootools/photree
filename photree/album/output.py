"""User-facing output formatting for album commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..common.formatting import CHECK, CROSS, WARNING  # noqa: F401

if TYPE_CHECKING:
    from .ios_fixes import FixIosResult


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
    return f"Done. Removed {total} non-HEIC duplicate(s): {parts}."


def miscategorized_summary(
    action: str,
    heic_from_orig: int,
    heic_from_rendered: int,
    mov_from_orig: int,
    mov_from_rendered: int,
) -> str:
    total = heic_from_orig + heic_from_rendered + mov_from_orig + mov_from_rendered
    if total == 0:
        return "Done. No miscategorized files found."
    verb = "Moved" if action == "mv" else "Removed"
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


def batch_check_summary(passed: int, failed: int, warned: int = 0) -> str:
    parts = [f"{passed} album(s) passed"]
    if warned:
        parts.append(f"{warned} with warnings")
    parts.append(f"{failed} failed")
    return f"\nDone. {', '.join(parts)}."


def optimize_summary(heic_count: int, mov_count: int, link_mode: str) -> str:
    parts = ", ".join(
        [
            *([f"{heic_count} heic"] if heic_count else []),
            *([f"{mov_count} mov"] if mov_count else []),
        ]
    )
    if parts:
        return f"Done. {parts} file(s) linked ({link_mode})."
    else:
        return "Done. Nothing to optimize."


def batch_optimize_summary(optimized: int, failed: int) -> str:
    return f"\nDone. {optimized} album(s) optimized, {failed} failed."


def batch_fix_ios_summary(fixed: int, failed: int) -> str:
    return f"\nDone. {fixed} album(s) fixed, {failed} failed."


def media_op_summary(
    verb: str,
    files_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    total = sum(len(files) for _, files in files_by_dir)
    if total == 0:
        return f"Done. No files to {verb.lower()}."
    parts = ", ".join(f"{len(files)} from {name}" for name, files in files_by_dir)
    return f"Done. {verb} {total} file(s): {parts}."


def format_fix_ios_result(result: FixIosResult) -> list[str]:
    """Format a :class:`FixIosResult` into output lines."""
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

    if result.rm_orphan_sidecar_removed_by_dir:
        lines.append(rm_orphan_sidecar_summary(result.rm_orphan_sidecar_removed_by_dir))

    if result.prefer_higher_quality_removed_by_dir:
        lines.append(
            prefer_higher_quality_summary(result.prefer_higher_quality_removed_by_dir)
        )

    if result.miscategorized_result is not None:
        mc = result.miscategorized_result
        lines.append(
            miscategorized_summary(
                action=mc.action,
                heic_from_orig=mc.heic_from_orig,
                heic_from_rendered=mc.heic_from_rendered,
                mov_from_orig=mc.mov_from_orig,
                mov_from_rendered=mc.mov_from_rendered,
            )
        )

    return lines


def media_op_check_suggestions(album_dirs: list[str]) -> str:
    lines = ["", "Suggested next steps:"]
    lines.extend(f'  photree album check --album-dir "{d}"' for d in album_dirs)
    return "\n".join(lines)
