"""Output formatting for album checks (preflight + integrity).

Formatters return unindented lines; nested detail lines are indented relative
to their heading with :func:`~photree.common.formatting.indent`, and the call
site decides how deep the whole block sits.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from textwrap import dedent

from rich.markup import escape

from ...clihelpers.sysdeps import format_missing_troubleshoot
from ...common.formatting import CHECK, CROSS, WARNING, format_check_line, indent
from ...common.fs import display_path
from ...common.sysdeps import SystemDependency
from ..faces.refresh import FaceFailure, format_face_failures
from ..id import format_album_external_id
from ..jpeg import JpegConversionFailure
from ..naming import AlbumNamingResult, BatchNamingResult, ExifTimestampCheck
from ..store.protocol import MediaSource
from . import AlbumIntegrityResult, AlbumMediaSourceSummary, AlbumPreflightResult
from .browsable import BrowsableDirCheck
from .dir_structure import AlbumDirCheck
from .exif_cache_state import ExifCacheStateCheck
from .face_state import FaceStateCheck, FaceSyncIssue, FaceSyncIssueKind
from .ios import (
    DuplicateNumber,
    IosMediaSourceIntegrityResult,
    MiscategorizedFile,
    MiscategorizedKind,
)
from .ios.sidecar import SidecarCheck, SidecarIssue, SidecarIssueKind
from .jpeg import AlbumJpegIntegrityResult, JpegCheck
from .media_metadata import MediaMetadataCheck
from .std import DuplicateStem, StdMediaSourceIntegrityResult
from .troubleshoot import suggest_exif_fixes, suggest_fixes
from .unexpected_dirs import UnexpectedDirsCheck


def _bullets(items: Sequence[str]) -> list[str]:
    """``- item`` lines, one level deeper than their heading."""
    return [indent(f"- {item}") for item in items]


# ---------------------------------------------------------------------------
# System check output
# ---------------------------------------------------------------------------


def jpeg_failures_report(
    failures: tuple[tuple[str, JpegConversionFailure], ...],
) -> str:
    """Format per-file JPEG conversion failures for a single album."""
    return "\n".join(
        [
            f"{CROSS} jpeg: {len(failures)} file(s) could not be converted",
            *(
                indent(escape(f"{source}/{failure.filename}: {failure.reason}"), 2)
                for source, failure in failures
            ),
        ]
    )


def face_failures_report(failures: tuple[tuple[str, FaceFailure], ...]) -> str:
    """Format per-image face detection failures for a single album."""
    return "\n".join(
        [
            f"{CROSS} face detection failed for {len(failures)} image(s)",
            *(indent(escape(line), 2) for line in format_face_failures(failures)),
        ]
    )


def derived_failures_report(
    jpeg_failures: tuple[tuple[str, JpegConversionFailure], ...],
    face_failures: tuple[tuple[str, FaceFailure], ...],
    album_dir: str,
) -> str:
    """JPEG and face-detection failures of a refresh, each with its retry command.

    Shared by every command that refreshes derived data (refresh, import,
    gallery import), so a partial refresh reads — and is retried — the same
    way everywhere. Rich markup, with user text escaped.
    """
    flag = escape(f'--album-dir "{album_dir}"')
    return "\n".join(
        [
            *(
                [
                    jpeg_failures_report(jpeg_failures),
                    (
                        f"Run 'photree album refresh --refresh-jpeg {flag}'"
                        " to retry the conversions."
                    ),
                ]
                if jpeg_failures
                else []
            ),
            *(
                [
                    face_failures_report(face_failures),
                    (
                        f"Run 'photree album detect-faces {flag}'"
                        " to retry face detection."
                    ),
                ]
                if face_failures
                else []
            ),
        ]
    )


def sips_check(available: bool) -> str:
    if available:
        return f"{CHECK} sips"
    else:
        return f"{CROSS} sips (not found)"


def sips_troubleshoot() -> str:
    return format_missing_troubleshoot([SystemDependency.SIPS])


def exiftool_check(available: bool) -> str:
    if available:
        return f"{CHECK} exiftool"
    else:
        return f"{CHECK} exiftool (not found, EXIF checks skipped)"


def exiftool_troubleshoot() -> str:
    return format_missing_troubleshoot([SystemDependency.EXIFTOOL])


# ---------------------------------------------------------------------------
# Album-level output
# ---------------------------------------------------------------------------


def media_sources_check(summary: AlbumMediaSourceSummary) -> str:
    if not summary.media_sources:
        return f"{CROSS} media sources: none detected"
    else:
        return f"{CHECK} media sources: {summary.description}"


def media_source_conflicts_check(conflicts: tuple[str, ...]) -> str:
    """Failed media sources line for an iOS/std name clash."""
    return format_check_line(
        "media sources",
        success=False,
        summary=(
            f"ios-<name>/ and std-<name>/ both present for: {', '.join(conflicts)}"
        ),
        details=(
            (
                "both would share the same browsable directories and media IDs;"
                " other media checks were skipped"
            ),
        ),
    )


def media_source_conflicts_troubleshoot(conflicts: tuple[str, ...]) -> str:
    names = ", ".join(conflicts)
    return (
        f"Media source name(s) used by both an iOS and a std archive: {names}.\n"
        "Rename one of the two archive directories (and its browsable "
        "directories) so every media source name is unique."
    )


def album_id_check_line(has_id: bool, album_id: str | None = None) -> str:
    if has_id and album_id is not None:
        return f"{CHECK} album id: {format_album_external_id(album_id)}"
    else:
        return f"{CROSS} album id: missing (.photree/album.yaml)"


def media_metadata_check_line(check: MediaMetadataCheck) -> str:
    stale_parts = [
        *([f"{len(check.new_keys)} new"] if check.new_keys else []),
        *([f"{len(check.stale_keys)} removed"] if check.stale_keys else []),
    ]
    match (check.has_media_metadata, check.duplicate_ids, stale_parts):
        case (False, _, _):
            return f"{CROSS} media metadata: missing"
        case (True, dups, _) if dups:
            return f"{CROSS} media metadata: {len(dups)} duplicate id(s)"
        case (True, _, parts) if parts:
            return f"{CROSS} media metadata: stale ({', '.join(parts)})"
        case _:
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


def unexpected_dirs_check_line(check: UnexpectedDirsCheck) -> str:
    if check.success:
        return f"{CHECK} no unexpected directories"
    else:
        return "\n".join(
            [
                f"{CROSS} unexpected directories:",
                *[indent(f"{d}/", 2) for d in check.unexpected],
            ]
        )


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
    return "\n".join(
        [
            *_format_naming_line(result),
            *_format_exif_line(result, fatal_exif=fatal_exif, album_dir=album_dir),
        ]
    )


def _format_naming_line(result: AlbumNamingResult) -> list[str]:
    if result.issues:
        return [
            f"{CROSS} naming: {len(result.issues)} issue(s)",
            *[indent(issue.message, 2) for issue in result.issues],
        ]
    else:
        return [f"{CHECK} naming"]


def _format_exif_line(
    result: AlbumNamingResult, *, fatal_exif: bool, album_dir: str
) -> list[str]:
    icon = CROSS if fatal_exif else WARNING
    match result.exif_check:
        case None:
            return []
        case ExifTimestampCheck(matches=True):
            return [f"{CHECK} exif timestamps match album date"]
        case exif_check:
            return [
                *_format_exif_mismatches(exif_check, icon, album_dir),
                *(
                    [
                        (
                            f"{icon} exif: no file matches the album date"
                            f" ({exif_check.album_date}) exactly"
                        )
                    ]
                    if exif_check.no_exact_album_date_match
                    else []
                ),
            ]


def _format_exif_mismatches(
    exif_check: ExifTimestampCheck, icon: str, album_dir: str
) -> list[str]:
    """Format EXIF mismatch details with examples and fix suggestions."""
    n = len(exif_check.mismatches)
    max_examples = 5
    return (
        [
            f"{icon} exif: {n} file(s) outside album date ({exif_check.album_date})",
            *[
                indent(f"{m.file_name}  {m.timestamp}", 2)
                for m in exif_check.mismatches[:max_examples]
            ],
            *(
                [indent(f"... and {n - max_examples} more", 2)]
                if n > max_examples
                else []
            ),
            "",
            *(
                indent(line)
                for line in suggest_exif_fixes(
                    exif_check.mismatches,
                    album_date=exif_check.album_date,
                    album_dir=album_dir,
                )
            ),
        ]
        if exif_check.mismatches
        else []
    )


def format_batch_naming_issues(result: BatchNamingResult) -> str:
    """Format cross-album naming issues (date collisions)."""
    if result.success:
        return f"{CHECK} no date collisions"
    else:
        return "\n".join(
            [
                f"{CROSS} date collisions: {len(result.date_collisions)} date(s)",
                *(
                    line
                    for album_date, albums in result.date_collisions
                    for line in (
                        indent(f"{album_date}:"),
                        *(indent(escape(album), 2) for album in albums),
                    )
                ),
            ]
        )


# ---------------------------------------------------------------------------
# Integrity output (was album/integrity/output.py)
# ---------------------------------------------------------------------------


def _issues_block(icon: str, label: str, issues: Sequence[str]) -> str:
    return "\n".join([f"{icon} {label}: {len(issues)} issue(s)", *_bullets(issues)])


def format_browsable_dir_check(label: str, check: BrowsableDirCheck) -> str:
    """Format a main directory check result."""
    if check.success:
        return f"{CHECK} {label}: {len(check.correct)} file(s) verified"
    else:
        issues = [
            *[
                f"missing: {m.filename} (expected from {m.source_dir}/)"
                for m in check.missing
            ],
            *[f"extra: {f}" for f in check.extra],
            *[
                f"wrong source: {w.filename} (should be {w.expected}, edited version exists)"
                for w in check.wrong_source
            ],
            *[
                f"wrong link mode: {w.filename} (expected {w.expected}, got {w.actual})"
                for w in check.wrong_link_mode
            ],
            *[
                f"size mismatch: {c.filename} (expected match with {c.expected_source})"
                for c in check.size_mismatches
            ],
            *[
                f"checksum mismatch: {c.filename} (expected match with {c.expected_source})"
                for c in check.checksum_mismatches
            ],
        ]
        return _issues_block(CROSS, label, issues)


def format_jpeg_check(check: JpegCheck, label: str) -> str:
    """Format a JPEG directory check result."""
    if check.success:
        return f"{CHECK} {label}: {len(check.present)} file(s) verified"
    else:
        issues = [
            *[f"missing: {f}" for f in check.missing],
            *[f"extra: {f}" for f in check.extra],
        ]
        return _issues_block(CROSS, label, issues)


def format_sidecar_issue(issue: SidecarIssue) -> str:
    match issue.kind:
        case SidecarIssueKind.MISSING_SIDECAR:
            return f"{issue.file} has no AAE sidecar in {issue.directory}/"
        case SidecarIssueKind.MISSING_EDIT_SIDECAR:
            return f"{issue.file} has no O-prefixed AAE sidecar in {issue.directory}/"
        case SidecarIssueKind.ORPHAN_SIDECAR:
            return f"{issue.file} has no matching media file in {issue.directory}/"
        case SidecarIssueKind.ORPHAN_EDIT_SIDECAR:
            return (
                f"{issue.file} has no matching edited media file in {issue.directory}/"
            )


def format_sidecar_check(check: SidecarCheck, *, fatal_sidecar: bool = False) -> str:
    """Format sidecar check result."""
    issues = [
        *(format_sidecar_issue(i) for i in check.orphan_sidecars),
        *(f"(info) {format_sidecar_issue(i)}" for i in check.missing_sidecars),
    ]
    if not issues:
        return f"{CHECK} sidecars"
    else:
        # CROSS if orphans (errors) or if missing sidecars are fatal; WARNING otherwise
        icon = CROSS if check.orphan_sidecars or fatal_sidecar else WARNING
        return _issues_block(icon, "sidecars", issues)


def format_duplicate_number(dup: DuplicateNumber) -> str:
    return (
        f"{dup.directory}/: number {dup.img_number} has multiple media files "
        f"with same prefix: {', '.join(dup.files)}"
    )


def format_duplicate_stem(dup: DuplicateStem) -> str:
    return (
        f"{dup.directory}/: stem {dup.stem} has multiple media files: "
        f"{', '.join(dup.files)}"
    )


def format_miscategorized_file(mf: MiscategorizedFile) -> str:
    match mf.kind:
        case MiscategorizedKind.EDITED_IN_ORIG:
            looks_like = "an edited file (IMG_E prefix)"
        case MiscategorizedKind.EDITED_SIDECAR_IN_ORIG:
            looks_like = "an edited sidecar (IMG_O prefix)"
        case MiscategorizedKind.ORIGINAL_IN_EDIT:
            looks_like = "an original file (no E/O prefix)"
        case MiscategorizedKind.ORIGINAL_SIDECAR_IN_EDIT:
            looks_like = "an original sidecar (no E/O prefix)"
    return f"{mf.file} in {mf.directory}/ looks like {looks_like}"


def format_duplicate_numbers(dups: tuple[DuplicateNumber, ...]) -> str | None:
    """Format duplicate number issues. Returns None if there are none."""
    return (
        _issues_block(
            CROSS, "duplicate numbers", [format_duplicate_number(d) for d in dups]
        )
        if dups
        else None
    )


def format_miscategorized(files: tuple[MiscategorizedFile, ...]) -> str | None:
    """Format miscategorized file issues. Returns None if there are none."""
    return (
        _issues_block(
            CROSS,
            "file categorization",
            [format_miscategorized_file(f) for f in files],
        )
        if files
        else None
    )


def format_duplicate_stems(dups: tuple[DuplicateStem, ...]) -> str:
    """Format duplicate stem issues of a std media source."""
    return (
        _issues_block(
            CROSS, "duplicate stems", [format_duplicate_stem(d) for d in dups]
        )
        if dups
        else f"{CHECK} no duplicate stems"
    )


def _format_browsable_and_jpeg(
    ms: MediaSource,
    result: IosMediaSourceIntegrityResult | StdMediaSourceIntegrityResult,
    p: str,
) -> list[str]:
    return [
        format_browsable_dir_check(f"{p}{ms.img_dir}", result.browsable_img),
        format_browsable_dir_check(f"{p}{ms.vid_dir}", result.browsable_vid),
        format_jpeg_check(result.browsable_jpg, f"{p}{ms.jpg_dir}"),
    ]


def _format_ios_media_source_integrity(
    ms: MediaSource,
    result: IosMediaSourceIntegrityResult,
    p: str,
    *,
    fatal_sidecar: bool,
) -> list[str]:
    """Format integrity checks for a single iOS media source."""
    return [
        *_format_browsable_and_jpeg(ms, result, p),
        format_sidecar_check(result.sidecars, fatal_sidecar=fatal_sidecar),
        format_duplicate_numbers(result.duplicate_numbers)
        or f"{CHECK} no duplicate numbers",
        format_miscategorized(result.miscategorized) or f"{CHECK} file categorization",
    ]


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
    return "\n".join(
        line
        for ms, ms_result in result.by_media_source
        for line in _format_media_source_section(
            ms,
            ms_result,
            f"[{ms.name}] " if multi else "",
            fatal_sidecar=fatal_sidecar,
        )
    )


def _format_media_source_section(
    ms: MediaSource,
    ms_result: IosMediaSourceIntegrityResult | StdMediaSourceIntegrityResult,
    p: str,
    *,
    fatal_sidecar: bool,
) -> list[str]:
    match ms_result:
        case IosMediaSourceIntegrityResult():
            return _format_ios_media_source_integrity(
                ms, ms_result, p, fatal_sidecar=fatal_sidecar
            )
        case StdMediaSourceIntegrityResult():
            return [
                *_format_browsable_and_jpeg(ms, ms_result, p),
                format_duplicate_stems(ms_result.duplicate_stems),
            ]


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
# Face state output
# ---------------------------------------------------------------------------


def format_face_sync_issue(issue: FaceSyncIssue) -> str:
    match issue.kind:
        case FaceSyncIssueKind.MISSING_NPZ:
            detail = ".yaml records faces but the .npz is missing"
        case FaceSyncIssueKind.MISSING_YAML:
            detail = ".npz exists but the .yaml state is missing"
        case FaceSyncIssueKind.KEYS_MISMATCH:
            detail = ".npz keys don't match .yaml processed-keys"
        case FaceSyncIssueKind.ARRAY_LENGTHS:
            detail = ".npz array lengths inconsistent"
    return f"{issue.media_source}: {detail}"


def format_face_state_check(check: FaceStateCheck) -> str:
    """Format face state check results."""
    if check.success:
        return f"{CHECK} face state"
    else:
        return "\n".join(
            [
                f"{CROSS} face state ({check.issue_count} issue(s))",
                *(
                    indent(line, 2)
                    for line in (
                        *(["model version mismatch"] if check.model_mismatch else []),
                        *(
                            format_face_sync_issue(e)
                            for e in check.npz_yaml_sync_errors
                        ),
                        (
                            "Run 'photree album refresh' or"
                            " 'photree album detect-faces --redetect' to fix."
                        ),
                    )
                ),
            ]
        )


def _format_issue_group(
    label: str, items: tuple[str, ...], *, max_shown: int = 5
) -> list[str]:
    """Format a group of issues with truncation."""
    return (
        [
            f"{label}: {', '.join(items[:max_shown])}",
            *(
                [f"... and {len(items) - max_shown} more"]
                if len(items) > max_shown
                else []
            ),
        ]
        if items
        else []
    )


# ---------------------------------------------------------------------------
# EXIF cache state output
# ---------------------------------------------------------------------------


def format_exif_cache_check(check: ExifCacheStateCheck) -> str:
    """Format EXIF cache state check results."""
    if check.success:
        return f"{CHECK} exif cache"
    else:
        return "\n".join(
            [
                f"{CROSS} exif cache ({check.issue_count} issue(s))",
                *(
                    indent(line, 2)
                    for line in (
                        *_format_issue_group("missing cache", check.missing_sources),
                        (
                            "Run 'photree album refresh' or"
                            " 'photree album check --refresh-exif-cache' to fix."
                        ),
                    )
                ),
            ]
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
    """Format all album preflight check lines, grouped by category."""
    sections = [
        _format_system_section(result),
        _format_structure_section(result),
        _format_media_section(result, fatal_sidecar=fatal_sidecar),
        _format_naming_section(result, fatal_exif=fatal_exif, album_dir=album_dir),
        _format_cache_section(result),
    ]
    return "\n\n".join(s for s in sections if s)


def _format_system_section(result: AlbumPreflightResult) -> str:
    return "\n".join(
        [
            "System:",
            sips_check(result.sips_available),
            exiftool_check(result.exiftool_available),
        ]
    )


def _format_structure_section(result: AlbumPreflightResult) -> str:
    id_check = result.album_id_check
    return "\n".join(
        [
            "Structure:",
            *(
                [album_id_check_line(id_check.has_id, id_check.album_id)]
                if id_check is not None
                else []
            ),
            *(
                [_directory_structure_line(result.dir_check)]
                if result.media_source_summary.media_sources
                else []
            ),
            *(
                [unexpected_dirs_check_line(result.unexpected_dirs_check)]
                if result.unexpected_dirs_check is not None
                else []
            ),
            (
                media_source_conflicts_check(result.media_source_conflicts)
                if result.media_source_conflicts
                else media_sources_check(result.media_source_summary)
            ),
            *(
                [media_metadata_check_line(result.media_metadata_check)]
                if result.media_metadata_check is not None
                else []
            ),
        ]
    )


def _directory_structure_line(check: AlbumDirCheck) -> str:
    """Collapsed directory structure check — single line on success, details on failure."""
    total_present = len(check.present) + len(check.optional_present)
    opt_absent = len(check.optional_absent)

    if not check.missing:
        parts = [
            f"{total_present} present",
            *([f"{opt_absent} optional absent"] if opt_absent else []),
        ]
        return format_check_line(
            "directory structure", success=True, summary=", ".join(parts)
        )
    else:
        return format_check_line(
            "directory structure",
            success=False,
            summary=f"{len(check.missing)} missing",
            details=(
                f"missing: {', '.join(check.missing)}",
                *([f"present: {', '.join(check.present)}"] if check.present else []),
            ),
        )


def _format_media_section(
    result: AlbumPreflightResult, *, fatal_sidecar: bool
) -> str | None:
    if result.integrity is None and result.jpeg_check is None:
        return None
    else:
        return "\n".join(
            [
                "Media:",
                *(
                    [
                        format_integrity_checks(
                            result.integrity, fatal_sidecar=fatal_sidecar
                        )
                    ]
                    if result.integrity is not None
                    else []
                ),
                *(
                    [format_jpeg_integrity_checks(result.jpeg_check)]
                    if result.jpeg_check is not None
                    else []
                ),
            ]
        )


def _format_naming_section(
    result: AlbumPreflightResult, *, fatal_exif: bool, album_dir: str
) -> str | None:
    if result.naming is None:
        return None
    else:
        return "\n".join(
            [
                "Naming:",
                format_naming_checks(
                    result.naming, fatal_exif=fatal_exif, album_dir=album_dir
                ),
            ]
        )


def _format_cache_section(result: AlbumPreflightResult) -> str | None:
    if result.face_state_check is None and result.exif_cache_check is None:
        return None
    else:
        return "\n".join(
            [
                "Cache:",
                *(
                    [format_face_state_check(result.face_state_check)]
                    if result.face_state_check is not None
                    else []
                ),
                *(
                    [format_exif_cache_check(result.exif_cache_check)]
                    if result.exif_cache_check is not None
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
    sidecar_issues = (
        [
            issue
            for _, ms_result in result.integrity.ios_results
            for issue in ms_result.sidecars.missing_sidecars
        ]
        if fatal_sidecar and result.integrity is not None
        else []
    )
    exif_mismatches = (
        list(result.naming.exif_check.mismatches)
        if fatal_exif
        and result.naming is not None
        and result.naming.exif_check is not None
        else []
    )
    return "\n".join(
        [
            "Failed due to fatal warning flags:",
            *(
                indent(f"{CROSS} sidecars: {format_sidecar_issue(i)}")
                for i in sidecar_issues
            ),
            *(
                indent(f"{CROSS} exif: {m.file_name}  {m.timestamp}")
                for m in exif_mismatches
            ),
        ]
    )


def _integrity_suggestions(
    result: AlbumPreflightResult, album_dir_flag: str
) -> list[str]:
    """Fix suggestions for every media source's integrity failures (iOS and std)."""
    return [
        suggestion
        for ms, ms_result in (
            result.integrity.by_media_source if result.integrity is not None else ()
        )
        for suggestion in suggest_fixes(ms_result, album_dir_flag, ms)
    ]


def _missing_dirs_suggestions(
    result: AlbumPreflightResult, album_dir_flag: str
) -> list[str]:
    """Missing browsable directories → suggest refresh --refresh-browsable."""
    missing_browsable = frozenset(result.dir_check.missing) & frozenset(
        d
        for ms in result.media_source_summary.media_sources
        for d in (ms.img_dir, ms.vid_dir, ms.jpg_dir)
    )
    return (
        [
            dedent(f"""\
                photree album refresh {album_dir_flag} --refresh-browsable
                  Rebuild browsable directories ({", ".join(sorted(missing_browsable))})
                  from archive sources, then regenerate JPEGs.""")
        ]
        if missing_browsable
        else []
    )


def _media_metadata_suggestions(
    result: AlbumPreflightResult, album_dir_flag: str
) -> list[str]:
    return (
        [
            dedent(f"""\
                photree album refresh {album_dir_flag}
                  Generate or update media IDs in .photree/media-ids/.""")
        ]
        if result.media_metadata_check is not None
        and not result.media_metadata_check.in_sync
        else []
    )


def format_album_preflight_troubleshoot(
    result: AlbumPreflightResult,
    album_dir: str = ".",
) -> str | None:
    """Format troubleshooting info for failed album checks. Returns None if no failures."""
    album_dir_flag = f'--album-dir "{album_dir}"'
    all_suggestions = [
        *_missing_dirs_suggestions(result, album_dir_flag),
        *_integrity_suggestions(result, album_dir_flag),
        *_media_metadata_suggestions(result, album_dir_flag),
    ]
    lines = [
        *([sips_troubleshoot()] if not result.sips_available else []),
        *(
            [media_source_conflicts_troubleshoot(result.media_source_conflicts)]
            if result.media_source_conflicts
            else []
        ),
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
    parts = [
        f"{passed} album(s) passed",
        *([f"{warned} with warnings"] if warned else []),
        f"{failed} failed",
    ]
    return f"\nDone. {', '.join(parts)}."


# ---------------------------------------------------------------------------
# Batch check output
#
# Rendering for a check lives here whatever its scope, next to the single-album
# formatters above — the batch CLI wrapper composes these rather than building
# its own strings, so there is one place to change how a check result reads.
# ---------------------------------------------------------------------------


def batch_system_checks(*, sips_available: bool, exiftool_available: bool) -> str:
    """The system-dependency block printed once before a batch check.

    Unlike the import/refresh gate, a check degrades rather than aborts when
    exiftool is absent, so this reports both rather than failing on either.
    """
    return "\n".join([sips_check(sips_available), exiftool_check(exiftool_available)])


def duplicate_ids_report(
    kind: str,
    duplicates: dict[str, list[Path]],
    base: Path,
    format_id: Callable[[str], str],
) -> str:
    """Format duplicate-ID findings. *kind* is ``"album"`` or ``"media"``."""
    return "\n".join(
        "\n".join(
            [
                f"{CROSS} duplicate {kind} id: {format_id(dup_id)}",
                *(indent(str(display_path(p, base)), 2) for p in paths),
            ]
        )
        for dup_id, paths in duplicates.items()
    )


def no_duplicate_ids_line(kind: str) -> str:
    """The success counterpart of :func:`duplicate_ids_report`."""
    return f"{CHECK} no duplicate {kind} ids"


def batch_check_retry_flags(
    *,
    fatal_warnings: bool,
    fatal_sidecar: bool,
    fatal_exif_date_match: bool,
) -> str:
    """Reconstruct the flags needed to reproduce a batch check on one album.

    A suggested command that silently drops the caller's flags would not
    reproduce the failure it is suggested for.
    """
    return "".join(
        [
            " --fatal-warnings" if fatal_warnings else "",
            " --fatal-sidecar" if fatal_sidecar else "",
            " --no-fatal-exif-date-match" if not fatal_exif_date_match else "",
        ]
    )
