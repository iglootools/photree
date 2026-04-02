"""Output formatting for album preflight checks."""

from __future__ import annotations

from textwrap import dedent

from rich.markup import escape

from ...common.formatting import CHECK, CROSS, WARNING
from .troubleshoot import suggest_exif_fixes, suggest_fixes
from ..naming import AlbumNamingResult, BatchNamingResult
from . import AlbumMediaSourceSummary, AlbumPreflightResult
from ...fs import format_album_external_id


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
    """Deprecated — use media_sources_check instead."""
    return f"{CHECK} album type: {album_type}"


def media_sources_check(summary: AlbumMediaSourceSummary) -> str:
    if not summary.media_sources:
        return f"{CROSS} media sources: none detected"
    return f"{CHECK} media sources: {summary.description}"


def album_id_check_line(has_id: bool, album_id: str | None = None) -> str:
    if has_id and album_id is not None:
        return f"{CHECK} album id: {format_album_external_id(album_id)}"
    else:
        return f"{CROSS} album id: missing (.photree/album.yaml)"


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


def format_naming_checks(
    result: AlbumNamingResult,
    *,
    fatal_exif: bool = False,
    album_dir: str = ".",
) -> str:
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
            icon = CROSS if fatal_exif else WARNING
            if result.exif_check.mismatches:
                n = len(result.exif_check.mismatches)
                lines.append(
                    f"{icon} exif: {n} file(s) outside album date"
                    f" ({result.exif_check.album_date})"
                )
                max_examples = 5
                for m in result.exif_check.mismatches[:max_examples]:
                    lines.append(f"    {m.file_name}  {m.timestamp}")
                remaining = n - max_examples
                if remaining > 0:
                    lines.append(f"    ... and {remaining} more")

                lines.append("")
                lines.extend(
                    suggest_exif_fixes(
                        result.exif_check.mismatches,
                        album_date=result.exif_check.album_date,
                        album_dir=album_dir,
                    )
                )
            if result.exif_check.no_exact_album_date_match:
                lines.append(
                    f"{icon} exif: no file matches the album date"
                    f" ({result.exif_check.album_date}) exactly"
                )

    return "\n".join(lines)


def format_batch_naming_issues(result: BatchNamingResult) -> str:
    """Format cross-album naming issues (date collisions)."""
    if result.success:
        return f"{CHECK} no date collisions"

    lines = [f"{CROSS} date collisions: {len(result.date_collisions)} date(s)"]
    for album_date, albums in result.date_collisions:
        lines.append(f"  {album_date}:")
        lines.extend(f"    {escape(album)}" for album in albums)
    return "\n".join(lines)


def format_album_preflight_checks(
    result: AlbumPreflightResult,
    *,
    fatal_sidecar: bool = False,
    fatal_exif: bool = False,
    album_dir: str = ".",
) -> str:
    """Format all album preflight check lines."""
    from ..integrity.output import format_integrity_checks, format_jpeg_integrity_checks

    return "\n".join(
        [
            sips_check(result.sips_available),
            exiftool_check(result.exiftool_available),
            media_sources_check(result.media_source_summary),
            *(
                [
                    album_id_check_line(
                        result.album_id_check.has_id,
                        result.album_id_check.album_id,
                    )
                ]
                if result.album_id_check is not None
                else []
            ),
            *(
                album_dir_check(
                    result.dir_check.present,
                    result.dir_check.missing,
                    result.dir_check.optional_present,
                    result.dir_check.optional_absent,
                ).splitlines()
                if result.media_source_summary.media_sources
                else []
            ),
            *(
                format_integrity_checks(
                    result.ios_integrity, fatal_sidecar=fatal_sidecar
                ).splitlines()
                if result.ios_integrity is not None
                else []
            ),
            *(
                format_jpeg_integrity_checks(result.jpeg_check).splitlines()
                if result.jpeg_check is not None
                else []
            ),
            *(
                format_naming_checks(
                    result.naming, fatal_exif=fatal_exif, album_dir=album_dir
                ).splitlines()
                if result.naming is not None
                else []
            ),
        ]
    )


def format_fatal_warnings(
    result: AlbumPreflightResult,
    *,
    fatal_sidecar: bool = True,
    fatal_exif: bool = True,
) -> str:
    """Format the warnings that caused failure due to fatal-warning flags."""
    lines = ["Failed due to fatal warning flags:"]

    if fatal_sidecar and result.ios_integrity is not None:
        for _, contrib_result in result.ios_integrity.by_media_source:
            lines.extend(
                f"  {CROSS} sidecars: {w}"
                for w in contrib_result.sidecars.missing_sidecars
            )

    if (
        fatal_exif
        and result.naming is not None
        and result.naming.exif_check is not None
    ):
        for m in result.naming.exif_check.mismatches:
            lines.append(f"  {CROSS} exif: {m.file_name}  {m.timestamp}")

    return "\n".join(lines)


def format_album_preflight_troubleshoot(
    result: AlbumPreflightResult,
    album_dir: str = ".",
) -> str | None:
    """Format troubleshooting info for failed album checks. Returns None if no failures."""
    album_dir_flag = f'--album-dir "{album_dir}"'

    all_suggestions = [
        suggestion
        for _, contrib_result in (
            result.ios_integrity.by_media_source
            if result.ios_integrity is not None
            else ()
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
