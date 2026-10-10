"""Batch import across multiple album directories."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple, Protocol

from ...common.fs import list_files
from ...fsprotocol import LinkMode
from ..faces.detect import FaceAnalyzerFactory
from ..faces.failures import format_face_failures
from ..jpeg import ConvertFile, convert_single_file
from ..store.protocol import ios_import_dir, std_import_dir
from . import album_import
from .album_import import (
    AlbumImportResult,
    TaskIssue,
    task_has_content,
    validate_album_import,
)
from .tasks import discover_import_tasks, has_import_tasks


class OnSkipped(Protocol):
    """Called for each album the batch does not attempt."""

    def __call__(self, album_name: str, reason: str, *, warn: bool = False) -> None: ...


@dataclass(frozen=True)
class AlbumScan:
    """Result of scanning a parent directory for importable albums."""

    no_selection: tuple[Path, ...] = ()
    empty_selection: tuple[Path, ...] = ()
    to_import: tuple[Path, ...] = ()


@dataclass(frozen=True)
class AlbumValidation:
    """Validation result for a single album (aggregated across its tasks)."""

    album_dir: Path
    errors: tuple[TaskIssue, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class ImportFailureStage(StrEnum):
    """What went wrong — and therefore what a retry has to run.

    ``IMPORT`` means the import itself did not complete (staging may still
    be in place, so re-running the import is the retry). The other stages
    are partial failures of an import that *did* complete: its staging was
    consumed, so re-running the import would find nothing to do.
    """

    IMPORT = "import"
    JPEG = "jpeg"
    FACES = "faces"
    UNPROCESSED_SELECTION = "unprocessed-selection"


class AlbumFailure(NamedTuple):
    """An album whose import was attempted and failed, with the reason.

    *stages* says which parts failed, so the CLI can suggest the command
    that actually retries each one.
    """

    album_dir: Path
    reason: str
    stages: frozenset[ImportFailureStage] = frozenset({ImportFailureStage.IMPORT})


@dataclass(frozen=True)
class BatchResult:
    """Result of a batch import run.

    *validation_failures* is non-empty when validation refused the batch, in
    which case nothing was imported and *failed* is empty.
    """

    imported: int = 0
    failed: tuple[AlbumFailure, ...] = ()
    validation_failures: tuple[AlbumValidation, ...] = ()
    scan: AlbumScan = AlbumScan()

    @property
    def skipped(self) -> int:
        """Albums that were never attempted (no staging entry, or an empty one).

        Failures are counted separately: an album whose import raised was
        attempted and needs reporting, not quiet lumping in with the skips.
        """
        return len(self.scan.no_selection) + len(self.scan.empty_selection)

    @property
    def failed_count(self) -> int:
        return len(self.failed)

    @property
    def success(self) -> bool:
        return not self.failed and not self.validation_failures


def scan_albums(albums_dir: Path) -> AlbumScan:
    """Scan immediate subdirectories for importable albums."""
    subdirs = sorted(p for p in albums_dir.iterdir() if p.is_dir())
    return categorize_albums(subdirs)


def _album_has_content(album_dir: Path) -> bool:
    return any(task_has_content(t) for t in discover_import_tasks(album_dir))


def _empty_task_reason(album_dir: Path) -> str:
    """Describe why an album with ``to-import-*`` entries has nothing to import.

    Names each empty staging dir so a likely user mistake (e.g. std files placed
    directly in the dir instead of under ``orig/``) is easy to spot.
    """
    parts = [
        (
            f"{ios_import_dir(t.name)} (empty selection)"
            if t.is_ios
            else f"{std_import_dir(t.name)} (no media in orig/ or edit/)"
        )
        for t in discover_import_tasks(album_dir)
        if not task_has_content(t)
    ]
    return "; ".join(parts) if parts else "nothing to import"


def categorize_albums(album_dirs: Sequence[Path]) -> AlbumScan:
    """Categorize album directories by their ``to-import-*`` state.

    - ``no_selection``: no ``to-import-*`` entry at all.
    - ``empty_selection``: has ``to-import-*`` entries but nothing to import.
    - ``to_import``: has at least one non-empty task.
    """
    with_tasks = {d for d in album_dirs if has_import_tasks(d)}

    return AlbumScan(
        no_selection=tuple(d for d in album_dirs if d not in with_tasks),
        empty_selection=tuple(
            d for d in album_dirs if d in with_tasks and not _album_has_content(d)
        ),
        to_import=tuple(
            d for d in album_dirs if d in with_tasks and _album_has_content(d)
        ),
    )


def validate_albums(
    albums: list[Path] | tuple[Path, ...],
    image_capture_files: list[str],
) -> list[AlbumValidation]:
    """Validate all albums' import tasks against the IC file list."""
    return [
        AlbumValidation(
            album_dir=album_dir,
            errors=validate_album_import(album_dir, image_capture_files).errors,
        )
        for album_dir in albums
    ]


# ---------------------------------------------------------------------------
# Batch run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ImportOptions:
    image_capture_dir: Path
    link_mode: LinkMode
    dry_run: bool
    convert_file: ConvertFile
    max_workers: int | None
    analyzer_factory: FaceAnalyzerFactory | None


@dataclass(frozen=True)
class _Callbacks:
    on_importing: Callable[[str], None] | None
    on_imported: Callable[[str], None] | None
    on_error: Callable[[str, str], None] | None


def _scan(albums_dir: Path | None, album_dirs: Sequence[Path] | None) -> AlbumScan:
    match (albums_dir, album_dirs):
        case (Path() as base, None):
            return scan_albums(base)
        case (None, [*dirs]):
            return categorize_albums(dirs)
        case _:
            raise ValueError("Exactly one of albums_dir or album_dirs must be provided")


def _report_skips(scan: AlbumScan, on_skipped: OnSkipped | None) -> None:
    if on_skipped:
        for album_dir in scan.no_selection:
            on_skipped(album_dir.name, "no to-import-{ios,std}-<name> directory")
        # A to-import-* dir that yields nothing is most likely a user mistake
        # (e.g. std files placed directly instead of under orig/) — warn, don't
        # skip silently like an album with no staging dir at all.
        for album_dir in scan.empty_selection:
            on_skipped(album_dir.name, _empty_task_reason(album_dir), warn=True)


def _result_failure(album_dir: Path, result: AlbumImportResult) -> AlbumFailure | None:
    """An import that ran to completion can still have failed in part.

    Every partial failure is reported: listing only the first would hide the
    others until the next run.
    """
    jpeg = "; ".join(
        f"{source}/{failure.filename}: {failure.reason}"
        for source, failure in result.jpeg_failures
    )
    faces = "; ".join(format_face_failures(result.face_failures))
    parts = [
        *(
            [
                (
                    ImportFailureStage.UNPROCESSED_SELECTION,
                    f"selection entries left behind: {', '.join(result.unprocessed)}",
                )
            ]
            if result.unprocessed
            else []
        ),
        *(
            [(ImportFailureStage.JPEG, f"jpeg conversion failed: {jpeg}")]
            if jpeg
            else []
        ),
        *(
            [(ImportFailureStage.FACES, f"face detection failed: {faces}")]
            if faces
            else []
        ),
    ]
    return (
        AlbumFailure(
            album_dir,
            "; ".join(reason for _, reason in parts),
            frozenset(stage for stage, _ in parts),
        )
        if parts
        else None
    )


def _import_one(
    album_dir: Path, options: _ImportOptions, callbacks: _Callbacks
) -> AlbumFailure | None:
    """Import one album, reporting the outcome through *callbacks*."""
    if callbacks.on_importing:
        callbacks.on_importing(album_dir.name)
    try:
        failure = _result_failure(
            album_dir,
            album_import.run_import(
                album_dir=album_dir,
                image_capture_dir=options.image_capture_dir,
                link_mode=options.link_mode,
                dry_run=options.dry_run,
                convert_file=options.convert_file,
                max_workers=options.max_workers,
                analyzer_factory=options.analyzer_factory,
            ),
        )
    # OSError rather than FileNotFoundError alone: a batch should report
    # any per-album filesystem failure and carry on, matching the gallery
    # batch importer. A missing system dependency is deliberately not
    # caught here — it is machine-wide, so it aborts the whole run.
    except (OSError, ValueError) as exc:
        failure = AlbumFailure(album_dir, str(exc))

    match failure:
        case None:
            if callbacks.on_imported:
                callbacks.on_imported(album_dir.name)
        case AlbumFailure(reason=reason):
            if callbacks.on_error:
                callbacks.on_error(album_dir.name, reason)
    return failure


def run_batch_import(
    *,
    albums_dir: Path | None = None,
    album_dirs: Sequence[Path] | None = None,
    image_capture_dir: Path,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_importing: Callable[[str], None] | None = None,
    on_imported: Callable[[str], None] | None = None,
    on_skipped: OnSkipped | None = None,
    on_error: Callable[[str, str], None] | None = None,
    on_validation_error: Callable[[str, list[TaskIssue]], None] | None = None,
    convert_file: ConvertFile = convert_single_file,
    max_workers: int | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
) -> BatchResult:
    """Run import for all albums with at least one non-empty import task.

    Provide exactly one of *albums_dir* (scan immediate subdirectories) or
    *album_dirs* (explicit list of album directories).

    Validates ALL albums before importing ANY. If any album fails validation,
    no imports are performed and the failures are returned in
    :attr:`BatchResult.validation_failures`.

    Callbacks are optional hooks for the CLI layer to print status:
    - ``on_importing(album_name)`` — called before importing an album
    - ``on_imported(album_name)`` — called after a successful album import
    - ``on_skipped(album_name, reason, warn=...)`` — called for each skipped album
    - ``on_error(album_name, error)`` — called when an album import fails
    - ``on_validation_error(album_name, errors)`` — called when validation fails
    """
    scan = _scan(albums_dir, album_dirs)
    _report_skips(scan, on_skipped)

    ic_files = list_files(image_capture_dir) if scan.to_import else []
    validation_failures = tuple(
        v for v in validate_albums(scan.to_import, ic_files) if not v.success
    )
    if validation_failures:
        if on_validation_error:
            for v in validation_failures:
                on_validation_error(v.album_dir.name, list(v.errors))
        return BatchResult(scan=scan, validation_failures=validation_failures)
    else:
        options = _ImportOptions(
            image_capture_dir=image_capture_dir,
            link_mode=link_mode,
            dry_run=dry_run,
            convert_file=convert_file,
            max_workers=max_workers,
            analyzer_factory=analyzer_factory,
        )
        callbacks = _Callbacks(on_importing, on_imported, on_error)
        outcomes = [_import_one(d, options, callbacks) for d in scan.to_import]
        failures = tuple(f for f in outcomes if f is not None)
        return BatchResult(
            imported=len(outcomes) - len(failures), failed=failures, scan=scan
        )
