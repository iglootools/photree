"""Fake import preflight check results for demo and testing purposes."""

from __future__ import annotations

from pathlib import Path

from ..preflight import (
    ImageCaptureDirCheck,
    ImportPreflightResult,
    SelectionDirStatus,
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
    sips_available=True,
    selection_dir_status=SelectionDirStatus.OK,
    selection_path=Path("/albums/trip-paris/to-import"),
    image_capture_dir=Path("~/Pictures/iPhone"),
    image_capture_dir_found=True,
    image_capture_dir_check=IC_CHECK_OK,
    image_capture_dir_preflight_skipped=False,
)

PREFLIGHT_FAILURES = ImportPreflightResult(
    sips_available=False,
    selection_dir_status=SelectionDirStatus.NOT_FOUND,
    selection_path=Path("/albums/trip-paris/to-import"),
    image_capture_dir=Path("~/Pictures/iPhone"),
    image_capture_dir_found=True,
    image_capture_dir_check=IC_CHECK_WARNINGS,
    image_capture_dir_preflight_skipped=False,
)
