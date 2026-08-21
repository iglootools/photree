"""User-facing messages for the importer."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from textwrap import dedent

from ...common.formatting import CHECK, CROSS
from ...common.fs import display_path
from .preflight import (
    _IMG_PREFIX_THRESHOLD,
    ImageCaptureDirCheck,
    ImportPreflightResult,
    SelectionStatus,
)


def import_tasks_check(
    album_dir: Path,
    *,
    found: bool,
    empty: bool = False,
) -> str:
    """Format the import-tasks check line."""
    match (found, empty):
        case (False, _):
            return (
                f"{CROSS} import tasks: {album_dir} "
                f"(no to-import-{{ios,std}}-<name> directory)"
            )
        case (True, True):
            return f"{CROSS} import tasks: {album_dir} (nothing to import)"
        case _:
            return f"{CHECK} import tasks: {album_dir}"


def import_tasks_troubleshoot(album_dir: Path) -> str:
    """Troubleshooting info when no importable tasks are found."""
    return dedent(f"""\
        Create an import staging directory inside your album directory.

        iOS (Image Capture selection — filenames matched by image number):

          mkdir -p "{album_dir}/to-import-ios-main"
          # Then: Photos > File > Export > Export Originals… into it,
          # or create {album_dir}/to-import-ios-main.csv (one filename per row).

        std (import the files directly):

          mkdir -p "{album_dir}/to-import-std-<name>/orig"
          # (optional) mkdir -p "{album_dir}/to-import-std-<name>/edit"
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
                    f"(expected at least {_IMG_PREFIX_THRESHOLD:.0%}). "
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
                    f"{', '.join(check.subdirectory_names)}. "
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
) -> str:
    """Format the image capture directory check line(s)."""
    match (found, check, preflight_skipped):
        case (False, _, _):
            return f"{CROSS} image capture directory: {image_capture_dir} (not found)"
        case (True, ImageCaptureDirCheck() as c, _) if not c.success:
            warnings = _format_ic_dir_warnings(c)
            bullet_list = "\n".join(f"  - {w}" for w in warnings)
            return (
                f"{CROSS} image capture directory: {image_capture_dir}\n{bullet_list}"
            )
        case (True, _, True):
            return f"{CHECK} image capture directory: {image_capture_dir} (preflight skipped)"
        case _:
            return f"{CHECK} image capture directory: {image_capture_dir}"


def format_preflight_checks(result: ImportPreflightResult) -> str:
    """Format all preflight check lines from a result."""
    from ...clihelpers.sysdeps import format_statuses

    return "\n".join(
        [
            # system dependencies (sips, exiftool)
            *([format_statuses(result.system_deps)] if result.system_deps else []),
            # import tasks
            *(
                [
                    {
                        SelectionStatus.OK: import_tasks_check(
                            result.selection_path, found=True
                        ),
                        SelectionStatus.NOT_FOUND: import_tasks_check(
                            result.selection_path, found=False
                        ),
                        SelectionStatus.EMPTY: import_tasks_check(
                            result.selection_path, found=True, empty=True
                        ),
                    }[result.selection_status]
                ]
                if result.selection_status is not None
                and result.selection_path is not None
                else []
            ),
            # image capture dir (only meaningful when an iOS task is present)
            *(
                [
                    image_capture_dir_check_output(
                        result.image_capture_dir,
                        found=result.image_capture_dir_found,
                        check=result.image_capture_dir_check,
                        preflight_skipped=result.image_capture_dir_preflight_skipped,
                    )
                ]
                if result.ios_import_required
                else []
            ),
        ]
    )


def format_preflight_troubleshoot(result: ImportPreflightResult) -> str | None:
    """Format troubleshooting info for failed checks. Returns None if no failures."""
    from ...clihelpers.sysdeps import format_missing_troubleshoot

    missing_deps = result.missing_system_deps
    lines = [
        *([format_missing_troubleshoot(missing_deps)] if missing_deps else []),
        *(
            [import_tasks_troubleshoot(result.selection_path)]
            if result.selection_status
            in (SelectionStatus.NOT_FOUND, SelectionStatus.EMPTY)
            and result.selection_path is not None
            else []
        ),
    ]
    return "\n".join(lines) if lines else None


def image_capture_dir_troubleshoot(check: ImageCaptureDirCheck) -> str:
    warnings = _format_ic_dir_warnings(check)
    bullet_list = "\n".join(f"  - {w}" for w in warnings)
    return (
        "The source directory does not look like an Image Capture folder:\n"
        "\n"
        f"{bullet_list}\n"
        "\n"
        "Use --force to skip this check and proceed anyway."
    )


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------


def batch_album_importing(album_name: str) -> str:
    return f"Importing: {album_name}"


def batch_album_skipped(album_name: str, reason: str) -> str:
    return f"Skipping:  {album_name} ({reason})"


def batch_summary(imported: int, skipped: int, failed: int = 0) -> str:
    return f"\nDone. {imported} album(s) imported, {failed} failed, {skipped} skipped."


def batch_failures(failures: Sequence[tuple[Path, str]], base: Path) -> str:
    """Format the per-album failure reasons of a batch import.

    The reason is what the batch loop swallowed previously; without it a run
    where every album failed was indistinguishable from one where every album
    was skipped.
    """
    return "\n".join(
        [
            "\nFailed albums:",
            *(
                f"  {display_path(album_dir, base)}\n    {reason}"
                for album_dir, reason in failures
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validation_errors(album_name: str, errors: list[str]) -> str:
    bullet_list = "\n".join(f"  - {e}" for e in errors)
    return f"Validation failed for {album_name}:\n{bullet_list}"


def unprocessed_selection_files(files: tuple[str, ...]) -> str:
    bullet_list = "\n".join(f"  - {f}" for f in files)
    return (
        "Unexpected: some selection files were not processed (this is a bug):\n"
        f"{bullet_list}"
    )
