"""User-facing messages for the importer.

Every formatter returns Rich markup with user-derived text (paths, album and
media source names, filenames, reasons) escaped via ``markup_escape``; print
the result with markup enabled. The exception is
:func:`format_archive_collision`, which is plain text because
:func:`format_task_issue` embeds and escapes it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from textwrap import dedent

from ...common.formatting import CHECK, CROSS, indent, markup_escape
from ...common.fs import display_path
from ..check.output import format_duplicate_stem
from ..check.std import DuplicateStem
from .album_import import (
    AlbumImportValidation,
    EmptyImageCaptureDirError,
    NoImportTasksError,
    TaskIssue,
    TaskIssueDetail,
)
from .batch import AlbumFailure
from .collision import ArchiveCollision
from .image_capture import (
    DedupWarning,
    ValidationError,
    ValidationErrorKind,
    ValidationWarning,
    ValidationWarningKind,
)
from .preflight import (
    IMG_PREFIX_THRESHOLD,
    ImageCaptureDirCheck,
    ImportPreflightResult,
    SelectionStatus,
)
from .std import StdNoMediaError

_MAX_COLLISIONS_SHOWN = 10


def _shown(path: Path, cwd: Path | None) -> str:
    """*path* relative to *cwd* (default: the process cwd), escaped for Rich."""
    return markup_escape(display_path(path, cwd if cwd is not None else Path.cwd()))


def _bullets(items: Sequence[str]) -> str:
    """``- item`` lines; *items* are Rich markup (escaped by the caller)."""
    return "\n".join(indent(f"- {item}") for item in items)


def import_tasks_check(
    album_dir: Path,
    *,
    found: bool,
    empty: bool = False,
    cwd: Path | None = None,
) -> str:
    """Format the import-tasks check line."""
    shown = _shown(album_dir, cwd)
    match (found, empty):
        case (False, _):
            return (
                f"{CROSS} import tasks: {shown} "
                f"(no to-import-{{ios,std}}-<name> directory)"
            )
        case (True, True):
            return f"{CROSS} import tasks: {shown} (nothing to import)"
        case _:
            return f"{CHECK} import tasks: {shown}"


def import_tasks_troubleshoot(album_dir: Path, *, cwd: Path | None = None) -> str:
    """Troubleshooting info when no importable tasks are found."""
    shown = _shown(album_dir, cwd)
    return dedent(f"""\
        Create an import staging directory inside your album directory.

        iOS (Image Capture selection — filenames matched by image number):

          mkdir -p "{shown}/to-import-ios-main"
          # Then: Photos > File > Export > Export Originals… into it,
          # or create {shown}/to-import-ios-main.csv (one filename per row).

        std (import the files directly):

          mkdir -p "{shown}/to-import-std-<name>/orig"
          # (optional) mkdir -p "{shown}/to-import-std-<name>/edit"
          # Then place the source files into orig/ (and edit/).""")


def _format_ic_dir_warnings(check: ImageCaptureDirCheck) -> list[str]:
    """Format warning strings from a structured IC directory check."""
    return [
        *(
            [
                "No recognized media files found (expected .heic, .jpg, .mov, .aae, etc.)."
            ]
            if not check.has_media_files
            else []
        ),
        *(
            [
                (
                    f"Only {check.img_prefixed_count}/{check.total_file_count} "
                    f"files ({check.img_prefix_ratio:.0%}) have the IMG_ prefix "
                    f"(expected at least {IMG_PREFIX_THRESHOLD:.0%}). "
                    f"This may not be an Image Capture directory."
                )
            ]
            if check.has_media_files and check.has_low_img_prefix_ratio
            else []
        ),
        *(
            [
                (
                    f"Found {len(check.subdirectory_names)} subdirectory(ies): "
                    f"{markup_escape(', '.join(check.subdirectory_names))}. "
                    f"Image Capture exports to a flat directory without subdirectories. "
                    f"You may be pointing at the wrong level "
                    f"(e.g. ~/Pictures instead of ~/Pictures/<Device>)."
                )
            ]
            if check.has_subdirectories
            else []
        ),
    ]


def image_capture_dir_check_output(
    image_capture_dir: Path,
    *,
    found: bool,
    check: ImageCaptureDirCheck | None = None,
    preflight_skipped: bool = False,
    cwd: Path | None = None,
) -> str:
    """Format the image capture directory check line(s)."""
    shown = _shown(image_capture_dir, cwd)
    match (found, check, preflight_skipped):
        case (False, _, _):
            return f"{CROSS} image capture directory: {shown} (not found)"
        case (True, ImageCaptureDirCheck() as c, _) if not c.success:
            bullet_list = _bullets(_format_ic_dir_warnings(c))
            return f"{CROSS} image capture directory: {shown}\n{bullet_list}"
        case (True, _, True):
            return f"{CHECK} image capture directory: {shown} (preflight skipped)"
        case _:
            return f"{CHECK} image capture directory: {shown}"


def _import_tasks_line(result: ImportPreflightResult, cwd: Path | None) -> list[str]:
    match (result.selection_status, result.selection_path):
        case (SelectionStatus.OK, Path() as path):
            return [import_tasks_check(path, found=True, cwd=cwd)]
        case (SelectionStatus.NOT_FOUND, Path() as path):
            return [import_tasks_check(path, found=False, cwd=cwd)]
        case (SelectionStatus.EMPTY, Path() as path):
            return [import_tasks_check(path, found=True, empty=True, cwd=cwd)]
        case _:
            return []


def format_preflight_checks(
    result: ImportPreflightResult, *, cwd: Path | None = None
) -> str:
    """Format all preflight check lines from a result."""
    from ...clihelpers.sysdeps import format_statuses

    return "\n".join(
        [
            # system dependencies (sips, exiftool)
            *([format_statuses(result.system_deps)] if result.system_deps else []),
            *_import_tasks_line(result, cwd),
            # image capture dir (only meaningful when an iOS task is present)
            *(
                [
                    image_capture_dir_check_output(
                        result.image_capture_dir,
                        found=result.image_capture_dir_found,
                        check=result.image_capture_dir_check,
                        preflight_skipped=result.image_capture_dir_preflight_skipped,
                        cwd=cwd,
                    )
                ]
                if result.ios_import_required
                else []
            ),
        ]
    )


def format_preflight_troubleshoot(
    result: ImportPreflightResult, *, cwd: Path | None = None
) -> str | None:
    """Format troubleshooting info for failed checks. Returns None if no failures."""
    from ...clihelpers.sysdeps import format_missing_troubleshoot

    missing_deps = result.missing_system_deps
    lines = [
        *([format_missing_troubleshoot(missing_deps)] if missing_deps else []),
        *(
            [import_tasks_troubleshoot(result.selection_path, cwd=cwd)]
            if result.selection_status
            in (SelectionStatus.NOT_FOUND, SelectionStatus.EMPTY)
            and result.selection_path is not None
            else []
        ),
    ]
    return "\n".join(lines) if lines else None


def image_capture_dir_troubleshoot(check: ImageCaptureDirCheck) -> str:
    return "\n".join(
        [
            "The source directory does not look like an Image Capture folder:",
            "",
            _bullets(_format_ic_dir_warnings(check)),
            "",
            "Use --force to skip this check and proceed anyway.",
        ]
    )


def import_error(exc: NoImportTasksError | EmptyImageCaptureDirError, cwd: Path) -> str:
    """Format a :func:`~photree.album.importer.album_import.run_import` refusal."""
    match exc:
        case NoImportTasksError(album_dir=album_dir):
            return (
                "No to-import-{ios,std}-<media-source> directories found in "
                f"{markup_escape(display_path(album_dir, cwd))}"
            )
        case EmptyImageCaptureDirError(image_capture_dir=ic_dir):
            return (
                "Could not find any image capture files in "
                f"{markup_escape(display_path(ic_dir, cwd))}"
            )


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


def batch_album_importing(album_name: str) -> str:
    return f"Importing: {markup_escape(album_name)}"


def batch_album_skipped(album_name: str, reason: str) -> str:
    return f"Skipping:  {markup_escape(album_name)} ({markup_escape(reason)})"


def batch_summary(imported: int, skipped: int, failed: int = 0) -> str:
    return f"\nDone. {imported} album(s) imported, {failed} failed, {skipped} skipped."


def batch_failures(failures: Sequence[AlbumFailure], base: Path) -> str:
    """Format the per-album failure reasons of a batch import.

    The reason is what the batch loop swallowed previously; without it a run
    where every album failed was indistinguishable from one where every album
    was skipped.
    """
    return "\n".join(
        [
            "\nFailed albums:",
            *(
                indent(
                    f"{markup_escape(display_path(failure.album_dir, base))}\n"
                    f"{indent(markup_escape(failure.reason))}"
                )
                for failure in failures
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _ios_error_message(error: ValidationError) -> str:
    files = ", ".join(error.files)
    n = error.img_number
    match error.kind:
        case ValidationErrorKind.NO_MATCHING_ORIGINAL:
            return "no matching original found in Image Capture directory"
        case ValidationErrorKind.MULTIPLE_ORIGINALS:
            return (
                f"expected 1 original media file for number {n} but found "
                f"{len(error.files)}: {files}. This may indicate a number "
                "collision with airdropped files."
            )
        case ValidationErrorKind.MULTIPLE_RENDERED:
            return (
                f"expected at most 1 rendered media file for number {n} but "
                f"found {len(error.files)}: {files}."
            )
        case ValidationErrorKind.ORPHAN_RENDERED_SIDECAR:
            return f"rendered sidecar exists ({files}) but no rendered media file"
        case ValidationErrorKind.MULTIPLE_LIVE_PHOTO_COMPANIONS:
            return (
                f"expected 1 Live Photo companion for number {n} but found "
                f"{len(error.files)}: {files}."
            )
        case ValidationErrorKind.MULTIPLE_RENDERED_LIVE_PHOTO_COMPANIONS:
            return (
                f"expected at most 1 rendered Live Photo companion for number "
                f"{n} but found {len(error.files)}: {files}."
            )


def _ios_warning_message(warning: ValidationWarning) -> str:
    match warning.kind:
        case ValidationWarningKind.MISSING_ORIGINAL_SIDECAR:
            return f"original HEIC ({warning.file}) has no AAE sidecar"
        case ValidationWarningKind.MISSING_RENDERED_SIDECAR:
            return (
                f"rendered file ({warning.file}) has no rendered sidecar (IMG_O*.AAE)"
            )


def format_archive_collision(collision: ArchiveCollision) -> str:
    """One-line description of an archive collision, with the way out.

    Plain text (print with ``markup=False``): :func:`format_task_issue`
    embeds it and escapes the whole line.
    """
    ms = collision.media_source
    keys = collision.keys
    shown = ", ".join(keys[:_MAX_COLLISIONS_SHOWN])
    more = (
        f" and {len(keys) - _MAX_COLLISIONS_SHOWN} more"
        if len(keys) > _MAX_COLLISIONS_SHOWN
        else ""
    )
    staging = f"to-import-{ms.media_source_type}-{ms.name}"
    return (
        f"import would conflict with {len(keys)} existing key(s) in media source "
        f"'{ms.name}': {shown}{more}. Rename {staging} to import into a different "
        "media source."
    )


def _task_issue_message(detail: TaskIssueDetail) -> str:
    match detail:
        case ValidationError() as error:
            return f"{error.selection_file}: {_ios_error_message(error)}"
        case ValidationWarning() as warning:
            return f"{warning.selection_file}: {_ios_warning_message(warning)}"
        case DedupWarning(img_number=n, kept=kept, dropped=dropped):
            return f"{dropped} dropped in favor of {kept} (duplicate number {n})"
        case StdNoMediaError():
            return "no media files found in orig/ or edit/"
        case DuplicateStem() as dup:
            return format_duplicate_stem(dup)
        case ArchiveCollision() as collision:
            return format_archive_collision(collision)


def format_task_issue(issue: TaskIssue) -> str:
    """Format one validation issue, prefixed with its ``[type:source]``.

    Escaped for Rich: the ``[ios:main]`` prefix would otherwise be parsed as
    a markup tag and silently dropped.
    """
    ms = issue.media_source
    return markup_escape(
        f"[{ms.media_source_type}:{ms.name}] {_task_issue_message(issue.detail)}"
    )


def validation_errors(album_name: str, errors: Sequence[TaskIssue]) -> str:
    bullet_list = _bullets([format_task_issue(e) for e in errors])
    return f"Validation failed for {markup_escape(album_name)}:\n{bullet_list}"


def _issue_section(title: str, issues: Sequence[TaskIssue]) -> list[str]:
    return (
        [f"{title}:\n{_bullets([format_task_issue(i) for i in issues])}"]
        if issues
        else []
    )


def validation_warnings(validation: AlbumImportValidation) -> str | None:
    """The non-blocking warnings of a validation (dedup first). None if none."""
    sections = [
        *_issue_section("Dedup Warnings", validation.dedup_warnings),
        *_issue_section("Warnings", validation.warnings),
    ]
    return "\n\n".join(sections) if sections else None


def unprocessed_selection_files(files: tuple[str, ...]) -> str:
    return "\n".join(
        [
            (
                "Some selection entries were imported but not removed from the "
                "staging dir or CSV."
            ),
            "Remove them before the next import, or it will conflict:",
            _bullets([markup_escape(f) for f in files]),
        ]
    )
