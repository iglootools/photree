"""Album import orchestrator.

Discovers all ``to-import-*`` tasks in an album, validates them, executes each
into its target media source (iOS via :mod:`image_capture`, std via
:mod:`std`), then refreshes all derived data once.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...common.fs import list_files
from ...fsprotocol import PHOTREE_DIR, LinkMode
from ..id import generate_album_id
from ..jpeg import convert_single_file
from ..store.metadata import save_album_metadata
from ..store.protocol import ALBUM_YAML, AlbumMetadata
from . import image_capture, std
from .image_capture import IosSourceImportResult, plan_import, validate_import_plan
from .selection import has_selection, read_selection
from .std import StdImportResult, validate_std_task
from .tasks import ImportTask, discover_import_tasks

if TYPE_CHECKING:
    from ..faces.detect import FaceAnalyzerFactory


STAGE_REFRESH_DERIVED = "refresh-derived"


def _ios_stage(name: str) -> str:
    return f"import-ios-{name}"


def _std_stage(name: str) -> str:
    return f"import-std-{name}"


def import_stage_labels(tasks: Sequence[ImportTask]) -> dict[str, str]:
    """Build ``StageProgressBar`` labels for an album's import tasks."""
    labels = {
        (_ios_stage(t.name) if t.is_ios else _std_stage(t.name)): (
            f"Importing {'ios' if t.is_ios else 'std'} source '{t.name}'"
        )
        for t in tasks
    }
    labels[STAGE_REFRESH_DERIVED] = "Refreshing derived data"
    return labels


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlbumImportValidation:
    """Aggregated validation for all of an album's import tasks."""

    album_dir: Path
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    dedup_warnings: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return not self.errors


def task_has_content(task: ImportTask) -> bool:
    """Return True if a task has anything to import (non-empty selection/media)."""
    if task.is_ios:
        return has_selection(task.selection_dir, task.selection_csv)
    return std.has_media(task)


def validate_album_import(
    album_dir: Path,
    image_capture_files: list[str],
) -> AlbumImportValidation:
    """Validate every import task in *album_dir* against *image_capture_files*.

    iOS tasks use the selection→plan validation; std tasks use
    :func:`photree.album.importer.std.validate_std_task`.
    """
    errors: list[str] = []
    warnings: list[str] = []
    dedup: list[str] = []

    for task in discover_import_tasks(album_dir):
        if task.is_ios:
            selection = list(
                read_selection(task.selection_dir, task.selection_csv).merged
            )
            plan = plan_import(selection, image_capture_files)
            plan_errors, plan_warnings = validate_import_plan(plan)
            errors.extend(
                f"[ios:{task.name}] {e.selection_file}: {e.message}"
                for e in plan_errors
            )
            warnings.extend(
                f"[ios:{task.name}] {w.selection_file}: {w.message}"
                for w in plan_warnings
            )
            dedup.extend(f"[ios:{task.name}] {d}" for d in plan.dedup_warnings)
        else:
            errors.extend(f"[std:{task.name}] {msg}" for msg in validate_std_task(task))

    return AlbumImportValidation(
        album_dir=album_dir,
        errors=tuple(errors),
        warnings=tuple(warnings),
        dedup_warnings=tuple(dedup),
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlbumImportResult:
    """Result of importing all of an album's tasks."""

    ios_results: tuple[IosSourceImportResult, ...] = ()
    std_results: tuple[StdImportResult, ...] = ()

    @property
    def unprocessed(self) -> tuple[str, ...]:
        """Matched iOS selection files that were somehow not processed (a bug)."""
        return tuple(f for r in self.ios_results for f in r.unprocessed)

    @property
    def processed(self) -> frozenset[str]:
        """All iOS selection files processed across every source."""
        return frozenset(f for r in self.ios_results for f in r.processed)


def _notify(callback: Callable[[str], None] | None, value: str) -> None:
    if callback:
        callback(value)


def _remove_empty_folders(root: Path) -> None:
    for dirpath, _dirnames, _filenames in list(os.walk(root))[::-1]:
        p = Path(dirpath)
        if p == root or p.name.startswith("."):
            continue
        if not os.listdir(dirpath):
            os.rmdir(dirpath)


def run_import(
    *,
    album_dir: Path,
    image_capture_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
    max_workers: int | None = None,
    exiftool: ExifToolHelper | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
) -> AlbumImportResult:
    """Import all ``to-import-*`` tasks in *album_dir*, then refresh derived data.

    Stages: one ``import-ios-<name>`` / ``import-std-<name>`` stage per task,
    then a final ``refresh-derived`` stage. The Image Capture directory is only
    consulted when at least one iOS task is present.

    Callbacks:
    - ``on_stage_start(stage)`` / ``on_stage_end(stage)`` — per-stage hooks.
    """
    tasks = discover_import_tasks(album_dir)
    if not tasks:
        raise FileNotFoundError(
            f"No to-import-{{ios,std}}-<media-source> directories found in {album_dir}"
        )

    ios_tasks = [t for t in tasks if t.is_ios]
    image_capture_files = list_files(image_capture_dir) if ios_tasks else []
    if ios_tasks and not image_capture_files:
        raise FileNotFoundError(
            f"Could not find any image capture files in {image_capture_dir}"
        )

    # Create album marker and metadata so gallery commands can discover this album
    if not dry_run:
        (album_dir / PHOTREE_DIR).mkdir(exist_ok=True)
        if not (album_dir / PHOTREE_DIR / ALBUM_YAML).is_file():
            save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))

    ios_results: list[IosSourceImportResult] = []
    std_results: list[StdImportResult] = []
    for task in tasks:
        if task.is_ios:
            _notify(on_stage_start, _ios_stage(task.name))
            ios_results.append(
                image_capture.import_ios_source(
                    album_dir,
                    task,
                    image_capture_dir,
                    image_capture_files,
                    dry_run=dry_run,
                )
            )
            _notify(on_stage_end, _ios_stage(task.name))
        else:
            _notify(on_stage_start, _std_stage(task.name))
            std_results.append(std.import_std_source(album_dir, task, dry_run=dry_run))
            _notify(on_stage_end, _std_stage(task.name))

    # Refresh all derived data once — discovers every media source and builds
    # browsable/JPEG/media-ids/EXIF cache/faces per source.
    _notify(on_stage_start, STAGE_REFRESH_DERIVED)
    from ..refresh import refresh_album_derived_data

    refresh_album_derived_data(
        album_dir,
        link_mode=link_mode,
        max_workers=max_workers,
        convert_file=convert_file,
        exiftool=exiftool,
        analyzer_factory=analyzer_factory,
        dry_run=dry_run,
    )
    _notify(on_stage_end, STAGE_REFRESH_DERIVED)

    if not dry_run:
        _remove_empty_folders(album_dir)

    return AlbumImportResult(
        ios_results=tuple(ios_results),
        std_results=tuple(std_results),
    )
