"""Output formatting for iOS album integrity checks."""

from __future__ import annotations

from ...uiconventions import CHECK, CROSS, WARNING
from . import (
    AlbumJpegIntegrityResult,
    CombinedDirCheck,
    IosAlbumFullIntegrityResult,
    IosAlbumIntegrityResult,
    JpegCheck,
    SidecarCheck,
)


def format_combined_dir_check(label: str, check: CombinedDirCheck) -> str:
    """Format a main directory check result."""
    if check.success:
        return f"{CHECK} {label}: {len(check.correct)} file(s) verified"
    else:
        issues = [
            *[
                f"  - missing: {m.filename} (expected from {m.source_dir}/)"
                for m in check.missing
            ],
            *[f"  - extra: {f}" for f in check.extra],
            *[f"  - wrong source: {f}" for f in check.wrong_source],
            *[
                f"  - size mismatch: {c.filename} (expected match with {c.expected_source})"
                for c in check.size_mismatches
            ],
            *[
                f"  - checksum mismatch: {c.filename} (expected match with {c.expected_source})"
                for c in check.checksum_mismatches
            ],
        ]
        return f"{CROSS} {label}: {len(issues)} issue(s)\n" + "\n".join(issues)


def format_jpeg_check(check: JpegCheck, label: str = "main-jpg") -> str:
    """Format a JPEG directory check result."""
    if check.success:
        return f"{CHECK} {label}: {len(check.present)} file(s) verified"
    else:
        issues = [
            *[f"  - missing: {f}" for f in check.missing],
            *[f"  - extra: {f}" for f in check.extra],
        ]
        return f"{CROSS} {label}: {len(issues)} issue(s)\n" + "\n".join(issues)


def format_sidecar_check(check: SidecarCheck, *, fatal_sidecar: bool = False) -> str:
    """Format sidecar check result."""
    lines: list[str] = []
    if check.orphan_sidecars:
        lines.extend(f"  - {w}" for w in check.orphan_sidecars)
    if check.missing_sidecars:
        lines.extend(f"  - (info) {w}" for w in check.missing_sidecars)

    if not lines:
        return f"{CHECK} sidecars"
    # CROSS if orphans (errors) or if missing sidecars are fatal; WARNING otherwise
    icon = CROSS if check.orphan_sidecars or fatal_sidecar else WARNING
    return f"{icon} sidecars: {len(lines)} issue(s)\n" + "\n".join(lines)


def format_duplicate_numbers(warnings: tuple[str, ...]) -> str | None:
    """Format duplicate number issues. Returns None if no warnings."""
    if not warnings:
        return None
    else:
        lines = [f"  - {w}" for w in warnings]
        return f"{CROSS} duplicate numbers: {len(warnings)} issues(s)\n" + "\n".join(
            lines
        )


def format_miscategorized(warnings: tuple[str, ...]) -> str | None:
    """Format miscategorized file issues. Returns None if no warnings."""
    if not warnings:
        return None
    else:
        lines = [f"  - {w}" for w in warnings]
        return f"{CROSS} file categorization: {len(warnings)} issues(s)\n" + "\n".join(
            lines
        )


def _format_media_source_integrity(
    result: IosAlbumIntegrityResult,
    prefix: str = "",
    *,
    fatal_sidecar: bool = False,
) -> str:
    """Format integrity checks for a single media source."""
    p = f"{prefix} " if prefix else ""
    sidecar_line = format_sidecar_check(result.sidecars, fatal_sidecar=fatal_sidecar)
    duplicate_line = (
        format_duplicate_numbers(result.duplicate_numbers) or ""
        if result.duplicate_numbers
        else f"{CHECK} no duplicate numbers"
    )
    miscategorized_line = (
        format_miscategorized(result.miscategorized) or ""
        if result.miscategorized
        else f"{CHECK} file categorization"
    )
    return "\n".join(
        [
            format_combined_dir_check(f"{p}main-img", result.combined_heic),
            format_combined_dir_check(f"{p}main-vid", result.combined_mov),
            format_jpeg_check(result.jpeg, f"{p}main-jpg"),
            sidecar_line,
            duplicate_line,
            miscategorized_line,
        ]
    )


def format_integrity_checks(
    result: IosAlbumFullIntegrityResult,
    *,
    fatal_sidecar: bool = False,
) -> str:
    """Format all integrity check lines across media sources.

    Single media source: no prefix (identical output to previous behavior).
    Multiple media sources: each section prefixed with ``[name]``.
    """
    multi = len(result.by_media_source) > 1
    return "\n".join(
        _format_media_source_integrity(
            ms_result,
            prefix=f"[{ms.name}]" if multi else "",
            fatal_sidecar=fatal_sidecar,
        )
        for ms, ms_result in result.by_media_source
    )


def format_jpeg_integrity_checks(result: AlbumJpegIntegrityResult) -> str:
    """Format JPEG integrity checks across all media sources."""
    multi = len(result.by_media_source) > 1
    return "\n".join(
        format_jpeg_check(
            check,
            f"{'[' + ms.name + '] ' if multi else ''}{ms.jpg_dir}",
        )
        for ms, check in result.by_media_source
    )
