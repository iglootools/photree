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

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...common.fs import list_files
from ...fsprotocol import PHOTREE_DIR, LinkMode
from ..faces.detect import FaceAnalyzerFactory
from ..faces.failures import FaceFailure
from ..id import generate_album_id
from ..jpeg import ConvertFile, JpegConversionFailure, convert_single_file
from ..refresh import AlbumRefreshResult, refresh_album_derived_data
from ..store.media_source import MediaSource, MediaSourceType
from ..store.metadata import save_album_metadata
from ..store.protocol import ALBUM_YAML, AlbumMetadata
from . import image_capture, std
from .collision import ArchiveCollision, ImportCollisionError
from .image_capture import (
    DedupWarning,
    IosSourceImportResult,
    ValidationError,
    ValidationWarning,
    validate_import_plan,
)
from .selection import has_selection
from .std import StdImportResult, StdValidationError, validate_std_task
from .tasks import ImportTask, discover_import_tasks

STAGE_REFRESH_DERIVED = "refresh-derived"


def _stage(task: ImportTask) -> str:
    return f"import-{task.media_source.media_source_type}-{task.name}"


def import_stage_labels(tasks: Sequence[ImportTask]) -> dict[str, str]:
    """Build ``StageProgressBar`` labels for an album's import tasks."""
    return {
        **{
            _stage(t): f"Importing {t.media_source.media_source_type} source '{t.name}'"
            for t in tasks
        },
        STAGE_REFRESH_DERIVED: "Refreshing derived data",
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


# What can be wrong with one import task. Errors are ValidationError,
# StdValidationError and ArchiveCollision; ValidationWarning and DedupWarning
# are informational.
TaskIssueDetail = (
    ValidationError
    | ValidationWarning
    | DedupWarning
    | StdValidationError
    | ArchiveCollision
)


@dataclass(frozen=True)
class TaskIssue:
    """An issue found while validating the import task for *media_source*."""

    media_source: MediaSource
    detail: TaskIssueDetail


@dataclass(frozen=True)
class AlbumImportValidation:
    """Aggregated validation for all of an album's import tasks."""

    album_dir: Path
    errors: tuple[TaskIssue, ...] = ()
    warnings: tuple[TaskIssue, ...] = ()
    dedup_warnings: tuple[TaskIssue, ...] = ()

    @property
    def success(self) -> bool:
        return not self.errors


def task_has_content(task: ImportTask) -> bool:
    """Return True if a task has anything to import (non-empty selection/media)."""
    match task.media_source.media_source_type:
        case MediaSourceType.IOS:
            return has_selection(task.selection_dir, task.selection_csv)
        case MediaSourceType.STD:
            return std.has_media(task)


def _issues(
    ms: MediaSource, details: Sequence[TaskIssueDetail]
) -> tuple[TaskIssue, ...]:
    return tuple(TaskIssue(ms, d) for d in details)


def _validate_ios_task(
    album_dir: Path, task: ImportTask, image_capture_files: list[str]
) -> AlbumImportValidation:
    ms = task.media_source
    plan = image_capture.plan_ios_task(task, image_capture_files)
    plan_errors, plan_warnings = validate_import_plan(plan)
    collision = image_capture.find_ios_collision(album_dir, ms, plan)
    return AlbumImportValidation(
        album_dir=album_dir,
        errors=_issues(ms, [*plan_errors, *([collision] if collision else [])]),
        warnings=_issues(ms, plan_warnings),
        dedup_warnings=_issues(ms, plan.dedup_warnings),
    )


def _validate_std_task(album_dir: Path, task: ImportTask) -> AlbumImportValidation:
    collision = std.find_std_collision(album_dir, task)
    return AlbumImportValidation(
        album_dir=album_dir,
        errors=_issues(
            task.media_source,
            [*validate_std_task(task), *([collision] if collision else [])],
        ),
    )


def _validate_task(
    album_dir: Path, task: ImportTask, image_capture_files: list[str]
) -> AlbumImportValidation:
    match task.media_source.media_source_type:
        case MediaSourceType.IOS:
            return _validate_ios_task(album_dir, task, image_capture_files)
        case MediaSourceType.STD:
            return _validate_std_task(album_dir, task)


def validate_album_import(
    album_dir: Path,
    image_capture_files: list[str],
) -> AlbumImportValidation:
    """Validate every import task in *album_dir* against *image_capture_files*.

    iOS tasks use the selection→plan validation; std tasks use
    :func:`photree.album.importer.std.validate_std_task`. Both also check for
    archive collisions, so every reason an import would be refused is known
    before anything is copied.
    """
    per_task = [
        _validate_task(album_dir, task, image_capture_files)
        for task in discover_import_tasks(album_dir)
    ]
    return AlbumImportValidation(
        album_dir=album_dir,
        errors=tuple(i for v in per_task for i in v.errors),
        warnings=tuple(i for v in per_task for i in v.warnings),
        dedup_warnings=tuple(i for v in per_task for i in v.dedup_warnings),
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


class NoImportTasksError(FileNotFoundError):
    """Raised when an album has no ``to-import-{ios,std}-<name>`` entry."""

    def __init__(self, album_dir: Path) -> None:
        self.album_dir = album_dir
        super().__init__(
            f"No to-import-{{ios,std}}-<media-source> directories found in {album_dir}"
        )


class EmptyImageCaptureDirError(FileNotFoundError):
    """Raised when an iOS task needs Image Capture files but there are none."""

    def __init__(self, image_capture_dir: Path) -> None:
        self.image_capture_dir = image_capture_dir
        super().__init__(
            f"Could not find any image capture files in {image_capture_dir}"
        )


@dataclass(frozen=True)
class AlbumImportResult:
    """Result of importing all of an album's tasks."""

    ios_results: tuple[IosSourceImportResult, ...] = ()
    std_results: tuple[StdImportResult, ...] = ()
    jpeg_failures: tuple[tuple[str, JpegConversionFailure], ...] = ()
    face_failures: tuple[tuple[str, FaceFailure], ...] = ()

    @property
    def unprocessed(self) -> tuple[str, ...]:
        """iOS selection entries left behind for a number that was imported."""
        return tuple(f for r in self.ios_results for f in r.unprocessed)

    @property
    def processed(self) -> frozenset[str]:
        """All iOS selection files processed across every source."""
        return frozenset(f for r in self.ios_results for f in r.processed)


def _notify(callback: Callable[[str], None] | None, value: str) -> None:
    if callback:
        callback(value)


def _remove_empty_folders(root: Path) -> None:
    # Bottom-up so a parent emptied by removing its children goes too.
    for dirpath in reversed([Path(d) for d, _, _ in os.walk(root)]):
        if (
            dirpath != root
            and not dirpath.name.startswith(".")
            and not os.listdir(dirpath)
        ):
            os.rmdir(dirpath)


def _require_tasks(album_dir: Path) -> list[ImportTask]:
    match discover_import_tasks(album_dir):
        case []:
            raise NoImportTasksError(album_dir)
        case tasks:
            return tasks


def _image_capture_files(
    tasks: Sequence[ImportTask], image_capture_dir: Path
) -> list[str]:
    """Image Capture files, read only when at least one iOS task needs them."""
    if not any(t.is_ios for t in tasks):
        return []
    else:
        files = list_files(image_capture_dir)
        if not files:
            raise EmptyImageCaptureDirError(image_capture_dir)
        else:
            return files


def _find_collision(
    album_dir: Path, task: ImportTask, image_capture_files: list[str]
) -> ArchiveCollision | None:
    match task.media_source.media_source_type:
        case MediaSourceType.IOS:
            plan = image_capture.plan_ios_task(task, image_capture_files)
            return image_capture.find_ios_collision(album_dir, task.media_source, plan)
        case MediaSourceType.STD:
            return std.find_std_collision(album_dir, task)


def _raise_on_collision(
    album_dir: Path, tasks: Sequence[ImportTask], image_capture_files: list[str]
) -> None:
    """Refuse the whole import before any mutation if any task would collide.

    Checking every task up front is what keeps a collision in a later task
    from leaving an earlier one imported with no derived-data refresh.
    """
    collision = next(
        (
            c
            for task in tasks
            if (c := _find_collision(album_dir, task, image_capture_files))
        ),
        None,
    )
    if collision is not None:
        raise ImportCollisionError.from_collision(collision)


def _ensure_album_metadata(album_dir: Path, new_id: Callable[[], str]) -> None:
    """Create the album marker and metadata so gallery commands discover it."""
    (album_dir / PHOTREE_DIR).mkdir(exist_ok=True)
    if not (album_dir / PHOTREE_DIR / ALBUM_YAML).is_file():
        save_album_metadata(album_dir, AlbumMetadata(id=new_id()))


def _import_task(
    album_dir: Path,
    task: ImportTask,
    image_capture_dir: Path,
    image_capture_files: list[str],
    *,
    dry_run: bool,
) -> IosSourceImportResult | StdImportResult:
    match task.media_source.media_source_type:
        case MediaSourceType.IOS:
            return image_capture.import_ios_source(
                album_dir,
                task,
                image_capture_dir,
                image_capture_files,
                dry_run=dry_run,
            )
        case MediaSourceType.STD:
            return std.import_std_source(album_dir, task, dry_run=dry_run)


def _run_task_stage(
    album_dir: Path,
    task: ImportTask,
    image_capture_dir: Path,
    image_capture_files: list[str],
    *,
    dry_run: bool,
    on_stage_start: Callable[[str], None] | None,
    on_stage_end: Callable[[str], None] | None,
) -> IosSourceImportResult | StdImportResult:
    """Import one task as its own progress stage."""
    _notify(on_stage_start, _stage(task))
    result = _import_task(
        album_dir, task, image_capture_dir, image_capture_files, dry_run=dry_run
    )
    _notify(on_stage_end, _stage(task))
    return result


def run_import(
    *,
    album_dir: Path,
    image_capture_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    convert_file: ConvertFile = convert_single_file,
    max_workers: int | None = None,
    exiftool: ExifToolHelper | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
    new_id: Callable[[], str] = generate_album_id,
) -> AlbumImportResult:
    """Import all ``to-import-*`` tasks in *album_dir*, then refresh derived data.

    Stages: one ``import-ios-<name>`` / ``import-std-<name>`` stage per task,
    then a final ``refresh-derived`` stage. The Image Capture directory is only
    consulted when at least one iOS task is present.

    Raises :class:`NoImportTasksError` / :class:`EmptyImageCaptureDirError`
    when there is nothing to import, and :class:`ImportCollisionError` — before
    touching the filesystem — when any task would overwrite archive keys.

    Callbacks:
    - ``on_stage_start(stage)`` / ``on_stage_end(stage)`` — per-stage hooks.
    """
    tasks = _require_tasks(album_dir)
    image_capture_files = _image_capture_files(tasks, image_capture_dir)
    _raise_on_collision(album_dir, tasks, image_capture_files)

    if not dry_run:
        _ensure_album_metadata(album_dir, new_id)

    results = [
        _run_task_stage(
            album_dir,
            task,
            image_capture_dir,
            image_capture_files,
            dry_run=dry_run,
            on_stage_start=on_stage_start,
            on_stage_end=on_stage_end,
        )
        for task in tasks
    ]
    refresh_result = _refresh_derived(
        album_dir,
        link_mode=link_mode,
        dry_run=dry_run,
        on_stage_start=on_stage_start,
        on_stage_end=on_stage_end,
        convert_file=convert_file,
        max_workers=max_workers,
        exiftool=exiftool,
        analyzer_factory=analyzer_factory,
    )

    if not dry_run:
        _remove_empty_folders(album_dir)

    return AlbumImportResult(
        ios_results=tuple(r for r in results if isinstance(r, IosSourceImportResult)),
        std_results=tuple(r for r in results if isinstance(r, StdImportResult)),
        jpeg_failures=refresh_result.jpeg_failures,
        face_failures=refresh_result.face_failures,
    )


def _refresh_derived(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    on_stage_start: Callable[[str], None] | None,
    on_stage_end: Callable[[str], None] | None,
    convert_file: ConvertFile,
    max_workers: int | None,
    exiftool: ExifToolHelper | None,
    analyzer_factory: FaceAnalyzerFactory | None,
) -> AlbumRefreshResult:
    """Refresh all derived data once, as the ``refresh-derived`` stage.

    Discovers every media source and builds browsable/JPEG/media-ids/EXIF
    cache/faces per source. Returns the refresh result, whose JPEG and face
    detection failures the import surfaces.
    """
    _notify(on_stage_start, STAGE_REFRESH_DERIVED)
    refresh_result = refresh_album_derived_data(
        album_dir,
        link_mode=link_mode,
        max_workers=max_workers,
        convert_file=convert_file,
        exiftool=exiftool,
        analyzer_factory=analyzer_factory,
        dry_run=dry_run,
    )
    _notify(on_stage_end, STAGE_REFRESH_DERIVED)
    return refresh_result
