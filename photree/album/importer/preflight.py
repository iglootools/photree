"""Pre-flight validation for import commands."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...common.sysdeps import (
    SystemDependency,
    SystemDependencyStatus,
    missing_dependencies,
)
from ...config import load_config
from .album_import import task_has_content
from .tasks import discover_import_tasks


def default_image_capture_dir(home: Path) -> Path:
    """Where Image Capture puts an iPhone's files by default."""
    return home / "Pictures" / "iPhone"


def resolve_image_capture_dir(
    source: Path | None,
    config_path: str | None,
    *,
    home: Callable[[], Path] = Path.home,
) -> Path:
    """Resolve the Image Capture directory: CLI flag > config > default.

    *home* is only called when neither the flag nor the config provides a
    directory, so tests can drive the fallback without touching ``$HOME``.

    Raises :class:`~photree.config.ConfigError` on config file errors.
    """
    if source is not None:
        # An explicit flag wins without reading a *searched-for* config, so a
        # broken config file cannot block an import that does not need it. An
        # explicit --config is still loaded: a path the user typed must not be
        # silently ignored.
        if config_path is not None:
            load_config(config_path)
        return source
    else:
        configured = load_config(config_path).importer.image_capture_dir
        return (
            configured if configured is not None else default_image_capture_dir(home())
        )


_KNOWN_EXTENSIONS = frozenset({".heic", ".jpg", ".jpeg", ".png", ".mov", ".aae"})
IMG_PREFIX_THRESHOLD = 0.5  # at least 50% of files must start with IMG_


class SelectionStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    EMPTY = "empty"


@dataclass(frozen=True)
class ImportPreflightResult:
    """Structured result of all import preflight checks."""

    system_deps: tuple[SystemDependencyStatus, ...]
    selection_status: SelectionStatus | None  # None if no album_dir provided
    selection_path: Path | None  # album dir (holds the to-import-* entries)
    image_capture_dir: Path
    image_capture_dir_found: bool
    image_capture_dir_check: ImageCaptureDirCheck | None  # None if not found or force
    image_capture_dir_preflight_skipped: bool
    ios_import_required: bool  # whether an Image Capture source is needed

    @property
    def missing_system_deps(self) -> tuple[SystemDependency, ...]:
        return missing_dependencies(self.system_deps)

    @property
    def success(self) -> bool:
        system_deps_ok = not self.missing_system_deps
        selection_ok = self.selection_status in (SelectionStatus.OK, None)
        ic_ok = self.image_capture_dir_found and (
            self.image_capture_dir_check is None or self.image_capture_dir_check.success
        )
        # The Image Capture directory only matters when an iOS task is present.
        return (
            system_deps_ok and selection_ok and (ic_ok or not self.ios_import_required)
        )


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
        return self.img_prefix_ratio < IMG_PREFIX_THRESHOLD

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


def _check_import_tasks(album_dir: Path) -> tuple[SelectionStatus, bool]:
    """Check import-task status for *album_dir*.

    Returns ``(status, ios_import_required)``.
    """
    tasks = discover_import_tasks(album_dir)
    ios_required = any(t.is_ios for t in tasks)
    if not tasks:
        status = SelectionStatus.NOT_FOUND
    elif any(task_has_content(t) for t in tasks):
        status = SelectionStatus.OK
    else:
        status = SelectionStatus.EMPTY
    return status, ios_required


def run_preflight(
    image_capture_dir: Path,
    *,
    system_deps: tuple[SystemDependencyStatus, ...] = (),
    album_dir: Path | None = None,
    force: bool = False,
) -> ImportPreflightResult:
    """Run all import preflight checks and return structured results.

    *system_deps* is probed by the caller rather than here, so this stays a
    pure function of the filesystem it is handed — PATH is the CLI layer's
    business, and tests can drive every branch without touching it.
    """
    if album_dir is not None:
        selection_status, ios_import_required = _check_import_tasks(album_dir)
        selection_path: Path | None = album_dir
    else:
        # No specific album — assume an iOS source may be needed (batch scan).
        selection_status, selection_path = None, None
        ios_import_required = True

    ic_found = image_capture_dir.is_dir()
    ic_check = (
        check_image_capture_dir(image_capture_dir) if ic_found and not force else None
    )

    return ImportPreflightResult(
        system_deps=system_deps,
        selection_status=selection_status,
        selection_path=selection_path,
        image_capture_dir=image_capture_dir,
        image_capture_dir_found=ic_found,
        image_capture_dir_check=ic_check,
        image_capture_dir_preflight_skipped=force,
        ios_import_required=ios_import_required,
    )
