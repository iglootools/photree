"""
Output formatting for one album's check (preflight + integrity).

Formatters return unindented lines; nested detail lines are indented relative
to their heading with :func:`~photree.common.formatting.indent`, and the call
site decides how deep the whole block sits.

Formatters return Rich markup: every user-derived value (album and media
source names, paths, filenames, issue messages) is escaped with
:func:`~photree.common.formatting.markup_escape` here, so callers print the
result with markup enabled and must not escape it again.
"""

from collections.abc import Sequence

from photree.album.check import (
    AlbumIntegrityResult,
    AlbumMediaSourceSummary,
    AlbumPreflightResult,
)
from photree.album.check.browsable import BrowsableDirCheck
from photree.album.check.dir_structure import AlbumDirCheck
from photree.album.check.exif_cache_state import ExifCacheStateCheck
from photree.album.check.exif_date import AlbumNamingResult, ExifTimestampCheck
from photree.album.check.face_state import (
    FaceStateCheck,
    FaceSyncIssue,
    FaceSyncIssueKind,
)
from photree.album.check.ios import (
    DuplicateNumber,
    IosMediaSourceIntegrityResult,
    MiscategorizedFile,
    MiscategorizedKind,
)
from photree.album.check.ios.sidecar import SidecarCheck, SidecarIssue, SidecarIssueKind
from photree.album.check.jpeg import AlbumJpegIntegrityResult, JpegCheck
from photree.album.check.media_metadata import MediaMetadataCheck
from photree.album.check.std import DuplicateStem, StdMediaSourceIntegrityResult
from photree.album.check.troubleshoot import suggest_exif_fixes
from photree.album.check.unexpected_dirs import UnexpectedDirsCheck
from photree.album.id import format_album_external_id
from photree.album.naming import BatchNamingResult
from photree.album.store.media_source import MediaSource
from photree.common.formatting import (
    CHECK,
    CROSS,
    WARNING,
    format_check_line,
    indent,
    markup_escape,
)


def _bullets(items: Sequence[str]) -> list[str]:
    """``- item`` lines (plain text, escaped), one level deeper than their heading."""
    return [indent(f"- {markup_escape(item)}") for item in items]


def sips_check(*, available: bool) -> str:
    """Format the sips availability line, as Rich markup."""
    if available:
        return f"{CHECK} sips"
    else:
        return f"{CROSS} sips (not found)"


def exiftool_check(*, available: bool) -> str:
    """
    Format the exiftool availability line, as Rich markup.

    A missing exiftool is not a failure: the EXIF checks are skipped.
    """
    if available:
        return f"{CHECK} exiftool"
    else:
        return f"{CHECK} exiftool (not found, EXIF checks skipped)"


def media_sources_check(summary: AlbumMediaSourceSummary) -> str:
    """Format the media sources line, as Rich markup."""
    if not summary.media_sources:
        return f"{CROSS} media sources: none detected"
    else:
        return f"{CHECK} media sources: {markup_escape(summary.description)}"


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


def album_id_check_line(*, has_id: bool, album_id: str | None = None) -> str:
    """Format the album ID line, as Rich markup."""
    if has_id and album_id is not None:
        return f"{CHECK} album id: {format_album_external_id(album_id)}"
    else:
        return f"{CROSS} album id: missing (.photree/album.yaml)"


def media_metadata_check_line(check: MediaMetadataCheck) -> str:
    """Format the media metadata line, as Rich markup."""
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


def unexpected_dirs_check_line(check: UnexpectedDirsCheck) -> str:
    """Format the unexpected directories check, as Rich markup."""
    if check.success:
        return f"{CHECK} no unexpected directories"
    else:
        return "\n".join(
            [
                f"{CROSS} unexpected directories:",
                *[indent(f"{markup_escape(d)}/", 2) for d in check.unexpected],
            ],
        )


def format_naming_checks(
    result: AlbumNamingResult,
    *,
    fatal_exif: bool = False,
    album_dir: str = ".",
) -> str:
    """Format the naming and EXIF date checks, as Rich markup."""
    return "\n".join(
        [
            *_format_naming_line(result),
            *_format_exif_line(result, fatal_exif=fatal_exif, album_dir=album_dir),
        ],
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
                        *(indent(markup_escape(album), 2) for album in albums),
                    )
                ),
            ],
        )


def _format_naming_line(result: AlbumNamingResult) -> list[str]:
    if result.issues:
        return [
            f"{CROSS} naming: {len(result.issues)} issue(s)",
            *[indent(markup_escape(issue.message), 2) for issue in result.issues],
        ]
    else:
        return [f"{CHECK} naming"]


def _format_exif_line(
    result: AlbumNamingResult,
    *,
    fatal_exif: bool,
    album_dir: str,
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
                        ),
                    ]
                    if exif_check.no_exact_album_date_match
                    else []
                ),
            ]


def _format_exif_mismatches(
    exif_check: ExifTimestampCheck,
    icon: str,
    album_dir: str,
) -> list[str]:
    n = len(exif_check.mismatches)
    max_examples = 5
    return (
        [
            f"{icon} exif: {n} file(s) outside album date ({exif_check.album_date})",
            *[
                indent(markup_escape(f"{m.file_name}  {m.timestamp}"), 2)
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


def _issues_block(icon: str, label: str, issues: Sequence[str]) -> str:
    """*label* and *issues* are plain text, escaped here."""
    return "\n".join(
        [f"{icon} {markup_escape(label)}: {len(issues)} issue(s)", *_bullets(issues)],
    )


def format_browsable_dir_check(label: str, check: BrowsableDirCheck) -> str:
    """Format one browsable directory's check, as Rich markup."""
    if check.success:
        return f"{CHECK} {markup_escape(label)}: {len(check.correct)} file(s) verified"
    else:
        issues = [
            *[
                f"missing: {m.filename} (expected from {m.source_dir}/)"
                for m in check.missing
            ],
            *[f"extra: {f}" for f in check.extra],
            *[
                f"wrong source: {w.filename} (should be "
                f"{w.expected}, edited version exists)"
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
                f"checksum mismatch: {c.filename} (expected "
                f"match with {c.expected_source})"
                for c in check.checksum_mismatches
            ],
        ]
        return _issues_block(CROSS, label, issues)


def format_jpeg_check(check: JpegCheck, label: str) -> str:
    """Format one JPEG directory's check, as Rich markup."""
    if check.success:
        return f"{CHECK} {markup_escape(label)}: {len(check.present)} file(s) verified"
    else:
        issues = [
            *[f"missing: {f}" for f in check.missing],
            *[f"extra: {f}" for f in check.extra],
        ]
        return _issues_block(CROSS, label, issues)


def format_sidecar_issue(issue: SidecarIssue) -> str:
    """Describe a sidecar issue in plain text (not escaped)."""
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
    """
    Format the sidecar check, as Rich markup.

    Missing sidecars are shown as warnings unless *fatal_sidecar* is set.
    """
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
    """Describe a duplicate image number in plain text (not escaped)."""
    return (
        f"{dup.directory}/: number {dup.img_number} has multiple media files "
        f"with same prefix: {', '.join(dup.files)}"
    )


def format_duplicate_stem(dup: DuplicateStem) -> str:
    """Describe a duplicate stem in plain text (not escaped)."""
    return (
        f"{dup.directory}/: stem {dup.stem} has multiple media files: "
        f"{', '.join(dup.files)}"
    )


def format_miscategorized_file(mf: MiscategorizedFile) -> str:
    """Describe a file in the wrong archive directory in plain text (not escaped)."""
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
            CROSS,
            "duplicate numbers",
            [format_duplicate_number(d) for d in dups],
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
    """Format the duplicate stems check, as Rich markup."""
    return (
        _issues_block(
            CROSS,
            "duplicate stems",
            [format_duplicate_stem(d) for d in dups],
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
    """
    Format the integrity checks of every media source.

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
                ms,
                ms_result,
                p,
                fatal_sidecar=fatal_sidecar,
            )
        case StdMediaSourceIntegrityResult():
            return [
                *_format_browsable_and_jpeg(ms, ms_result, p),
                format_duplicate_stems(ms_result.duplicate_stems),
            ]


def format_jpeg_integrity_checks(result: AlbumJpegIntegrityResult) -> str:
    """Format the JPEG check of each media source, as Rich markup."""
    multi = len(result.by_media_source) > 1
    return "\n".join(
        format_jpeg_check(
            check,
            f"{'[' + ms.name + '] ' if multi else ''}{ms.jpg_dir}",
        )
        for ms, check in result.by_media_source
    )


def format_face_sync_issue(issue: FaceSyncIssue) -> str:
    """Describe a face ``.npz``/``.yaml`` sync issue in plain text (not escaped)."""
    match issue.kind:
        case FaceSyncIssueKind.MISSING_NPZ:
            detail = ".yaml records faces but the .npz is missing"
        case FaceSyncIssueKind.MISSING_YAML:
            detail = ".npz exists but the .yaml state is missing"
        case FaceSyncIssueKind.KEYS_MISMATCH:
            detail = ".npz keys don't match .yaml processed-keys"
        case FaceSyncIssueKind.ARRAY_LENGTHS:
            detail = ".npz array lengths inconsistent"
        case FaceSyncIssueKind.LEGACY_NPZ:
            detail = ".npz is in a format this photree no longer reads"
    return f"{issue.media_source}: {detail}"


def format_face_state_check(check: FaceStateCheck) -> str:
    """Format the face state check, as Rich markup."""
    if check.success:
        return f"{CHECK} face state"
    else:
        return "\n".join(
            [
                f"{CROSS} face state ({check.issue_count} issue(s))",
                *(
                    indent(markup_escape(line), 2)
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
            ],
        )


def _format_issue_group(
    label: str,
    items: tuple[str, ...],
    *,
    max_shown: int = 5,
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


def format_exif_cache_check(check: ExifCacheStateCheck) -> str:
    """Format the EXIF cache check, as Rich markup."""
    if check.success:
        return f"{CHECK} exif cache"
    else:
        return "\n".join(
            [
                f"{CROSS} exif cache ({check.issue_count} issue(s))",
                *(
                    indent(markup_escape(line), 2)
                    for line in (
                        *_format_issue_group("missing cache", check.missing_sources),
                        (
                            "Run 'photree album refresh' or"
                            " 'photree album check --refresh-exif-cache' to fix."
                        ),
                    )
                ),
            ],
        )


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
            sips_check(available=result.sips_available),
            exiftool_check(available=result.exiftool_available),
        ],
    )


def _format_structure_section(result: AlbumPreflightResult) -> str:
    id_check = result.album_id_check
    return "\n".join(
        [
            "Structure:",
            *(
                [
                    album_id_check_line(
                        has_id=id_check.has_id,
                        album_id=id_check.album_id,
                    ),
                ]
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
        ],
    )


def _directory_structure_line(check: AlbumDirCheck) -> str:
    """Format the directory structure check: one line on success, details on failure."""
    total_present = len(check.present) + len(check.optional_present)
    opt_absent = len(check.optional_absent)

    if not check.missing:
        parts = [
            f"{total_present} present",
            *([f"{opt_absent} optional absent"] if opt_absent else []),
        ]
        return format_check_line(
            "directory structure",
            success=True,
            summary=", ".join(parts),
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
    result: AlbumPreflightResult,
    *,
    fatal_sidecar: bool,
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
                            result.integrity,
                            fatal_sidecar=fatal_sidecar,
                        ),
                    ]
                    if result.integrity is not None
                    else []
                ),
                *(
                    [format_jpeg_integrity_checks(result.jpeg_check)]
                    if result.jpeg_check is not None
                    else []
                ),
            ],
        )


def _format_naming_section(
    result: AlbumPreflightResult,
    *,
    fatal_exif: bool,
    album_dir: str,
) -> str | None:
    if result.naming is None:
        return None
    else:
        return "\n".join(
            [
                "Naming:",
                format_naming_checks(
                    result.naming,
                    fatal_exif=fatal_exif,
                    album_dir=album_dir,
                ),
            ],
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
            ],
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
                indent(f"{CROSS} sidecars: {markup_escape(format_sidecar_issue(i))}")
                for i in sidecar_issues
            ),
            *(
                indent(
                    f"{CROSS} exif: {markup_escape(f'{m.file_name}  {m.timestamp}')}",
                )
                for m in exif_mismatches
            ),
        ],
    )
