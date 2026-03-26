"""Output formatting for album preflight checks."""

from __future__ import annotations

from textwrap import dedent

from . import CHECK, CROSS
from .troubleshoot import suggest_fixes
from ..naming import AlbumNamingResult, BatchNamingResult
from ..preflight import AlbumPreflightResult, AlbumType


def sips_check(available: bool) -> str:
    if available:
        return f"{CHECK} sips"
    else:
        return f"{CROSS} sips (not found)"


def sips_troubleshoot() -> str:
    return dedent("""\
        sips: The macOS 'sips' tool is required for HEIC-to-JPEG conversion.
        sips is included with macOS. If you are running on a non-macOS system,
        HEIC-to-JPEG conversion is not supported.""")


def exiftool_check(available: bool) -> str:
    if available:
        return f"{CHECK} exiftool"
    else:
        return f"{CHECK} exiftool (not found, EXIF checks skipped)"


def exiftool_troubleshoot() -> str:
    return dedent("""\
        exiftool: Install via: brew install exiftool (macOS)
        or apt install libimage-exiftool-perl (Linux).""")


def album_type_check(album_type: str) -> str:
    return f"{CHECK} album type: {album_type}"


def album_dir_check(
    present: tuple[str, ...],
    missing: tuple[str, ...],
    optional_present: tuple[str, ...] = (),
    optional_absent: tuple[str, ...] = (),
) -> str:
    lines = [
        *[f"{CHECK} dir: {d}/" for d in present],
        *[f"{CROSS} dir: {d}/ (missing)" for d in missing],
        *[f"{CHECK} dir: {d}/ (optional)" for d in optional_present],
        *[f"{CHECK} dir: {d}/ (optional, absent)" for d in optional_absent],
    ]
    return "\n".join(lines)


def format_naming_checks(result: AlbumNamingResult) -> str:
    """Format naming validation results."""
    lines: list[str] = []

    if result.issues:
        lines.append(f"{CROSS} naming: {len(result.issues)} issue(s)")
        lines.extend(f"    {issue.message}" for issue in result.issues)
    else:
        lines.append(f"{CHECK} naming")

    if result.exif_check is not None:
        if result.exif_check.matches:
            lines.append(f"{CHECK} exif timestamps match album date")
        else:
            lines.append(
                f"{CROSS} exif timestamps do not match album date"
                f" ({result.exif_check.album_date})"
            )

    return "\n".join(lines)


def format_batch_naming_issues(result: BatchNamingResult) -> str:
    """Format cross-album naming issues (date collisions)."""
    if result.success:
        return f"{CHECK} no date collisions"

    lines = [f"{CROSS} date collisions: {len(result.date_collisions)} date(s)"]
    for album_date, albums in result.date_collisions:
        lines.append(f"  {album_date}:")
        lines.extend(f"    {album}" for album in albums)
    return "\n".join(lines)


def format_album_preflight_checks(result: AlbumPreflightResult) -> str:
    """Format all album preflight check lines."""
    from .integrity import format_integrity_checks

    return "\n".join(
        [
            sips_check(result.sips_available),
            exiftool_check(result.exiftool_available),
            album_type_check(result.album_type),
            *(
                album_dir_check(
                    result.dir_check.present,
                    result.dir_check.missing,
                    result.dir_check.optional_present,
                    result.dir_check.optional_absent,
                ).splitlines()
                if result.album_type == AlbumType.IOS
                else []
            ),
            *(
                format_integrity_checks(result.integrity).splitlines()
                if result.integrity is not None
                else []
            ),
            *(
                format_naming_checks(result.naming).splitlines()
                if result.naming is not None
                else []
            ),
        ]
    )


def format_album_preflight_troubleshoot(
    result: AlbumPreflightResult,
    album_dir: str = ".",
) -> str | None:
    """Format troubleshooting info for failed album checks. Returns None if no failures."""
    album_dir_flag = f'--album-dir "{album_dir}"'

    all_suggestions = [
        suggestion
        for _, contrib_result in (
            result.integrity.by_contributor if result.integrity is not None else ()
        )
        for suggestion in suggest_fixes(contrib_result, album_dir_flag)
    ]

    lines = [
        *([sips_troubleshoot()] if not result.sips_available else []),
        *(
            [
                "Suggested fixes (remove --dry-run to apply):\n\n"
                + "\n\n".join(all_suggestions)
            ]
            if all_suggestions
            else []
        ),
    ]
    return "\n".join(lines) if lines else None
