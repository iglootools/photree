"""Output formatting for album preflight checks."""

from __future__ import annotations

from textwrap import dedent

from . import CHECK, CROSS
from .troubleshoot import suggest_fixes
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


def format_album_preflight_checks(result: AlbumPreflightResult) -> str:
    """Format all album preflight check lines."""
    from .integrity import format_integrity_checks

    return "\n".join(
        [
            sips_check(result.sips_available),
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
        ]
    )


def format_album_preflight_troubleshoot(
    result: AlbumPreflightResult,
    album_dir: str = ".",
) -> str | None:
    """Format troubleshooting info for failed album checks. Returns None if no failures."""
    album_dir_flag = f'--album-dir "{album_dir}"'

    lines = [
        *([sips_troubleshoot()] if not result.sips_available else []),
        *(
            [
                "Suggested fixes (remove --dry-run to apply):\n\n"
                + "\n\n".join(suggestions)
            ]
            if result.integrity is not None
            and (suggestions := suggest_fixes(result.integrity, album_dir_flag))
            else []
        ),
    ]
    return "\n".join(lines) if lines else None
