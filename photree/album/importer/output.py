"""User-facing messages for the importer."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from ...common.formatting import CHECK, CROSS
from ..store.protocol import SELECTION_DIR
from .image_capture import ValidationError
from .preflight import (
    _IMG_PREFIX_THRESHOLD,
    ImageCaptureDirCheck,
    ImportPreflightResult,
    SelectionDirStatus,
)


def selection_dir_check(
    selection_path: Path,
    *,
    found: bool,
    empty: bool = False,
) -> str:
    """Format the selection directory check line."""
    match (found, empty):
        case (False, _):
            return f"{CROSS} {SELECTION_DIR}/: {selection_path} (not found)"
        case (True, True):
            return f"{CROSS} {SELECTION_DIR}/: {selection_path} (empty)"
        case _:
            return f"{CHECK} {SELECTION_DIR}/: {selection_path}"


def selection_dir_troubleshoot(selection_path: Path, *, found: bool) -> str:
    """Troubleshooting info for the selection directory."""
    if found:
        return dedent(f"""\
            {SELECTION_DIR}/: Export your photo selection from the Photos app into this folder:

              Photos > File > Export > Export Originals… into {selection_path}""")
    else:
        return dedent(f"""\
            {SELECTION_DIR}/: Create the folder inside your album directory and export
            your photo selection from the Photos app into it:

              mkdir -p "{selection_path}"
              # Then: Photos > File > Export > Export Originals… into {selection_path}""")


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
                f"Only {check.img_prefixed_count}/{check.total_file_count} "
                f"files ({check.img_prefix_ratio:.0%}) have the IMG_ prefix "
                f"(expected at least {_IMG_PREFIX_THRESHOLD:.0%}). "
                f"This may not be an Image Capture directory."
            ]
            if check.has_media_files and check.has_low_img_prefix_ratio
            else []
        ),
        *(
            [
                f"Found {len(check.subdirectory_names)} subdirectory(ies): "
                f"{', '.join(check.subdirectory_names)}. "
                f"Image Capture exports to a flat directory without subdirectories. "
                f"You may be pointing at the wrong level "
                f"(e.g. ~/Pictures instead of ~/Pictures/<Device>)."
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
    from ..preflight.output import sips_check

    return "\n".join(
        [
            # sips
            *(
                [sips_check(result.sips_available)]
                if result.sips_available is not None
                else []
            ),
            # selection dir
            *(
                [
                    {
                        SelectionDirStatus.OK: selection_dir_check(
                            result.selection_path, found=True
                        ),
                        SelectionDirStatus.NOT_FOUND: selection_dir_check(
                            result.selection_path, found=False
                        ),
                        SelectionDirStatus.EMPTY: selection_dir_check(
                            result.selection_path, found=True, empty=True
                        ),
                    }[result.selection_dir_status]
                ]
                if result.selection_dir_status is not None
                and result.selection_path is not None
                else []
            ),
            # image capture dir
            image_capture_dir_check_output(
                result.image_capture_dir,
                found=result.image_capture_dir_found,
                check=result.image_capture_dir_check,
                preflight_skipped=result.image_capture_dir_preflight_skipped,
            ),
        ]
    )


def format_preflight_troubleshoot(result: ImportPreflightResult) -> str | None:
    """Format troubleshooting info for failed checks. Returns None if no failures."""
    from ..preflight.output import sips_troubleshoot

    lines = [
        *([sips_troubleshoot()] if result.sips_available is False else []),
        *(
            [
                selection_dir_troubleshoot(
                    result.selection_path,
                    found=result.selection_dir_status != SelectionDirStatus.NOT_FOUND,
                )
            ]
            if result.selection_dir_status
            in (SelectionDirStatus.NOT_FOUND, SelectionDirStatus.EMPTY)
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
# Batch (image-capture-all)
# ---------------------------------------------------------------------------


def batch_album_importing(album_name: str) -> str:
    return f"Importing: {album_name}"


def batch_album_skipped(album_name: str, reason: str) -> str:
    return f"Skipping:  {album_name} ({reason})"


def batch_summary(imported: int, skipped: int) -> str:
    return f"\nDone. {imported} album(s) imported, {skipped} skipped."


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validation_errors(album_name: str, errors: list[ValidationError]) -> str:
    bullet_list = "\n".join(f"  - [{e.selection_file}] {e.message}" for e in errors)
    return f"Validation failed for {album_name}:\n{bullet_list}"


def unprocessed_selection_files(files: tuple[str, ...]) -> str:
    bullet_list = "\n".join(f"  - {f}" for f in files)
    return (
        "Unexpected: some selection files were not processed (this is a bug):\n"
        f"{bullet_list}"
    )
