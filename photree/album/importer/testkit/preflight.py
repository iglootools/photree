"""Fake import preflight check results for demo and testing purposes."""

from __future__ import annotations

from pathlib import Path

from ....common.sysdeps import SystemDependency, SystemDependencyStatus
from ..preflight import (
    ImageCaptureDirCheck,
    ImportPreflightResult,
    SelectionStatus,
)


def _deps(*, available: bool) -> tuple[SystemDependencyStatus, ...]:
    return tuple(
        SystemDependencyStatus(dependency=dependency, available=available)
        for dependency in (SystemDependency.SIPS, SystemDependency.EXIFTOOL)
    )


IC_CHECK_OK = ImageCaptureDirCheck(
    has_media_files=True,
    img_prefixed_count=95,
    total_file_count=100,
    subdirectory_names=(),
)

IC_CHECK_WARNINGS = ImageCaptureDirCheck(
    has_media_files=True,
    img_prefixed_count=2,
    total_file_count=10,
    subdirectory_names=("albums", "backup", "temp"),
)

PREFLIGHT_OK = ImportPreflightResult(
    system_deps=_deps(available=True),
    selection_status=SelectionStatus.OK,
    selection_path=Path("/albums/trip-paris"),
    image_capture_dir=Path("~/Pictures/iPhone"),
    image_capture_dir_found=True,
    image_capture_dir_check=IC_CHECK_OK,
    image_capture_dir_preflight_skipped=False,
    ios_import_required=True,
)

PREFLIGHT_FAILURES = ImportPreflightResult(
    system_deps=_deps(available=False),
    selection_status=SelectionStatus.NOT_FOUND,
    selection_path=Path("/albums/trip-paris"),
    image_capture_dir=Path("~/Pictures/iPhone"),
    image_capture_dir_found=True,
    image_capture_dir_check=IC_CHECK_WARNINGS,
    image_capture_dir_preflight_skipped=False,
    ios_import_required=True,
)
