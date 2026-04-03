"""Output formatting for album checks (preflight + integrity)."""

from __future__ import annotations

from textwrap import dedent

from rich.markup import escape

from ...common.formatting import CHECK, CROSS, WARNING
from ..naming import AlbumNamingResult, BatchNamingResult
from ..id import format_album_external_id
from . import AlbumIntegrityResult, AlbumMediaSourceSummary, AlbumPreflightResult
from .media_metadata import MediaMetadataCheck
from .browsable import BrowsableDirCheck
from .ios import IosMediaSourceIntegrityResult
from .jpeg import AlbumJpegIntegrityResult, JpegCheck
from .ios.sidecar import SidecarCheck
from .troubleshoot import suggest_exif_fixes, suggest_fixes


# ---------------------------------------------------------------------------
# System check output
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Album-level output
# ---------------------------------------------------------------------------


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


def media_metadata_check_line(check: MediaMetadataCheck) -> str:
    if not check.has_media_metadata:
        return f"{CROSS} media metadata: missing"
    if check.duplicate_ids:
        return f"{CROSS} media metadata: {len(check.duplicate_ids)} duplicate id(s)"
    if check.new_keys or check.stale_keys:
        parts = [
            *(
                [f"{len(check.new_keys)} new"]
                if check.new_keys
                else []
            ),
            *(
                [f"{len(check.stale_keys)} removed"]
                if check.stale_keys
                else []
            ),
        ]
        return f"{CROSS} media metadata: stale ({', '.join(parts)})"
    return (
        f"{CHECK} media metadata: {check.image_count} image(s),"
        f" {check.video_count} video(s)"
    )


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


# ---------------------------------------------------------------------------
# Naming / EXIF output
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Integrity output (was album/integrity/output.py)
# ---------------------------------------------------------------------------


def format_browsable_dir_check(label: str, check: BrowsableDirCheck) -> str:
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


def _format_ios_media_source_integrity(
    result: IosMediaSourceIntegrityResult,
    prefix: str = "",
    *,
    fatal_sidecar: bool = False,
) -> str:
    """Format integrity checks for a single iOS media source."""
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
            format_browsable_dir_check(f"{p}main-img", result.browsable_img),
            format_browsable_dir_check(f"{p}main-vid", result.browsable_vid),
            format_jpeg_check(result.browsable_jpg, f"{p}main-jpg"),
            sidecar_line,
            duplicate_line,
            miscategorized_line,
        ]
    )


def format_integrity_checks(
    result: AlbumIntegrityResult,
    *,
    fatal_sidecar: bool = False,
) -> str:
    """Format all integrity check lines across media sources.

    Single media source: no prefix (identical output to previous behavior).
    Multiple media sources: each section prefixed with ``[name]``.
    """
    multi = len(result.by_media_source) > 1
    lines: list[str] = []
    for ms, ms_result in result.by_media_source:
        prefix = f"[{ms.name}]" if multi else ""
        p = f"{prefix} " if prefix else ""
        if isinstance(ms_result, IosMediaSourceIntegrityResult):
            lines.append(
                _format_ios_media_source_integrity(
                    ms_result, prefix=prefix, fatal_sidecar=fatal_sidecar
                )
            )
        else:
            # Std media source — browsable + jpeg checks, no sidecars
            lines.append(
                "\n".join(
                    [
                        format_browsable_dir_check(
                            f"{p}{ms.img_dir}", ms_result.browsable_img
                        ),
                        format_browsable_dir_check(
                            f"{p}{ms.vid_dir}", ms_result.browsable_vid
                        ),
                        format_jpeg_check(ms_result.browsable_jpg, f"{p}{ms.jpg_dir}"),
                    ]
                )
            )
    return "\n".join(lines)


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


# ---------------------------------------------------------------------------
# Preflight orchestration output
# ---------------------------------------------------------------------------


def format_album_preflight_checks(
    result: AlbumPreflightResult,
    *,
    fatal_sidecar: bool = False,
    fatal_exif: bool = False,
    album_dir: str = ".",
) -> str:
    """Format all album preflight check lines."""
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
                [media_metadata_check_line(result.media_metadata_check)]
                if result.media_metadata_check is not None
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
                    result.integrity, fatal_sidecar=fatal_sidecar
                ).splitlines()
                if result.integrity is not None
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

    if fatal_sidecar and result.integrity is not None:
        for _, contrib_result in result.integrity.ios_results:
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

    integrity_suggestions = [
        suggestion
        for _, contrib_result in (
            result.integrity.ios_results if result.integrity is not None else ()
        )
        for suggestion in suggest_fixes(contrib_result, album_dir_flag)
    ]

    media_metadata_suggestions = [
        *(
            [
                dedent(f"""\
                    photree album refresh {album_dir_flag}
                      Generate or update media IDs in .photree/media.yaml.""")
            ]
            if result.media_metadata_check is not None
            and not result.media_metadata_check.in_sync
            else []
        ),
    ]

    all_suggestions = [*integrity_suggestions, *media_metadata_suggestions]

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


def batch_check_summary(passed: int, failed: int, warned: int = 0) -> str:
    parts = [f"{passed} album(s) passed"]
    if warned:
        parts.append(f"{warned} with warnings")
    parts.append(f"{failed} failed")
    return f"\nDone. {', '.join(parts)}."
