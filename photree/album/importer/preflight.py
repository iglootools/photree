"""Pre-flight validation for import commands."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..preflight import check_sips_available
from ...fsprotocol import SELECTION_DIR

_KNOWN_EXTENSIONS = frozenset({".heic", ".jpg", ".jpeg", ".png", ".mov", ".aae"})
_IMG_PREFIX_THRESHOLD = 0.5  # at least 50% of files must start with IMG_


class SelectionDirStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    EMPTY = "empty"


@dataclass(frozen=True)
class ImportPreflightResult:
    """Structured result of all import preflight checks."""

    sips_available: bool | None  # None if skipped
    selection_dir_status: SelectionDirStatus | None  # None if no album_dir provided
    selection_path: Path | None
    image_capture_dir: Path
    image_capture_dir_found: bool
    image_capture_dir_check: ImageCaptureDirCheck | None  # None if not found or force
    image_capture_dir_preflight_skipped: bool

    @property
    def success(self) -> bool:
        sips_ok = self.sips_available is not False
        selection_ok = self.selection_dir_status in (SelectionDirStatus.OK, None)
        ic_ok = self.image_capture_dir_found and (
            self.image_capture_dir_check is None or self.image_capture_dir_check.success
        )
        return sips_ok and selection_ok and ic_ok


@dataclass(frozen=True)
class ImageCaptureDirCheck:
    """Structured result of checking an Image Capture source directory."""

    has_media_files: bool
    img_prefixed_count: int
    total_file_count: int
    subdirectory_names: tuple[str, ...]

    @property
    def img_prefix_ratio(self) -> float:
        return (
            self.img_prefixed_count / self.total_file_count
            if self.total_file_count
            else 0.0
        )

    @property
    def has_low_img_prefix_ratio(self) -> bool:
        return self.img_prefix_ratio < _IMG_PREFIX_THRESHOLD

    @property
    def has_subdirectories(self) -> bool:
        return len(self.subdirectory_names) > 0

    @property
    def success(self) -> bool:
        return (
            self.has_media_files
            and not self.has_low_img_prefix_ratio
            and not self.has_subdirectories
        )


def check_image_capture_dir(path: Path) -> ImageCaptureDirCheck:
    """Check whether *path* looks like an Image Capture output directory."""
    entries = os.listdir(path)
    files = [e for e in entries if (path / e).is_file()]
    subdirs = [e for e in entries if (path / e).is_dir()]

    return ImageCaptureDirCheck(
        has_media_files=any(Path(f).suffix.lower() in _KNOWN_EXTENSIONS for f in files),
        img_prefixed_count=sum(1 for f in files if f.upper().startswith("IMG_")),
        total_file_count=len(files),
        subdirectory_names=tuple(sorted(subdirs)[:5]),
    )


def _check_selection_dir(
    album_dir: Path,
) -> tuple[SelectionDirStatus, Path]:
    """Check the selection directory status."""
    selection_path = album_dir / SELECTION_DIR
    if not selection_path.is_dir():
        return SelectionDirStatus.NOT_FOUND, selection_path
    elif not any(selection_path.iterdir()):
        return SelectionDirStatus.EMPTY, selection_path
    else:
        return SelectionDirStatus.OK, selection_path


def run_preflight(
    image_capture_dir: Path,
    *,
    album_dir: Path | None = None,
    force: bool = False,
    skip_heic_to_jpeg: bool = False,
) -> ImportPreflightResult:
    """Run all import preflight checks and return structured results."""
    sips_available = None if skip_heic_to_jpeg else check_sips_available()

    if album_dir is not None:
        selection_status, selection_path = _check_selection_dir(album_dir)
    else:
        selection_status, selection_path = None, None

    ic_found = image_capture_dir.is_dir()
    ic_check = (
        check_image_capture_dir(image_capture_dir) if ic_found and not force else None
    )

    return ImportPreflightResult(
        sips_available=sips_available,
        selection_dir_status=selection_status,
        selection_path=selection_path,
        image_capture_dir=image_capture_dir,
        image_capture_dir_found=ic_found,
        image_capture_dir_check=ic_check,
        image_capture_dir_preflight_skipped=force,
    )
