import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from photree.album.faces.detect import (
    FaceAnalyzerFactory,
    memoized_face_analyzer_factory,
)
from photree.common.exif import ExifTagReader, exiftool_session
from photree.common.sysdeps import WhichFn
from photree.foundation.linking import LinkMode
from photree.gallery import importer as gallery_importer
from photree.gallery.import_plan import AlbumPlan, ImportAction
from photree.gallery.importer import AlbumImportResult, FaceFailures, JpegFailures


def _execute_plan(
    plan: AlbumPlan,
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    exiftool: ExifTagReader | None = None,
    analyzer_factory: FaceAnalyzerFactory | None = None,
    max_workers: int | None = None,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
) -> AlbumImportResult:
    """Dispatch a single plan to import or reimport."""
    match plan.action, plan.existing:
        case ImportAction.REIMPORT, Path() as existing:
            return gallery_importer.reimport_album(
                source_dir=plan.source,
                gallery_dir=gallery_dir,
                existing_dir=existing,
                link_mode=link_mode,
                dry_run=dry_run,
                on_stage_start=on_stage_start,
                on_stage_end=on_stage_end,
                max_workers=max_workers,
                exiftool=exiftool,
                analyzer_factory=analyzer_factory,
            )
        case ImportAction.NEW, _:
            return gallery_importer.import_album(
                source_dir=plan.source,
                gallery_dir=gallery_dir,
                link_mode=link_mode,
                dry_run=dry_run,
                on_stage_start=on_stage_start,
                on_stage_end=on_stage_end,
                max_workers=max_workers,
                exiftool=exiftool,
                analyzer_factory=analyzer_factory,
            )
        case action, existing:
            # SKIP plans are filtered out by the caller, and the planner
            # always attaches the existing dir to a REIMPORT plan.
            raise ValueError(
                f"cannot execute a {action} plan (existing dir: {existing})"
            )


def run_single_import(
    plan: AlbumPlan,
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    max_workers: int | None = None,
    which: WhichFn = shutil.which,
) -> AlbumImportResult:
    """Execute a single album import/reimport with optional stage callbacks.

    Creates a shared exiftool and injects a memoized face analyzer factory
    (loaded lazily, only if a source has images to detect).
    Raises :class:`ValueError` or :class:`OSError` on import errors.
    """
    with exiftool_session(which=which) as exiftool:
        return _execute_plan(
            plan,
            gallery_dir,
            link_mode,
            dry_run,
            exiftool=exiftool,
            analyzer_factory=memoized_face_analyzer_factory(),
            max_workers=max_workers,
            on_stage_start=on_stage_start,
            on_stage_end=on_stage_end,
        )


@dataclass(frozen=True)
class AlbumImportFailure:
    """Why one album of a batch did not import cleanly.

    Either *error* is set (the import raised, nothing was placed in the
    gallery) or *jpeg_failures* / *face_failures* are non-empty (the album
    imported, but some JPEGs are missing or some images are missing from face
    clustering).
    """

    source: Path
    error: ValueError | OSError | None = None
    jpeg_failures: JpegFailures = ()
    face_failures: FaceFailures = ()


@dataclass(frozen=True)
class BatchImportResult:
    imported: tuple[Path, ...] = ()
    failures: tuple[AlbumImportFailure, ...] = ()

    @property
    def failed_albums(self) -> tuple[Path, ...]:
        return tuple(f.source for f in self.failures)


def _import_one(
    plan: AlbumPlan,
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    exiftool: ExifTagReader | None,
    analyzer_factory: FaceAnalyzerFactory,
    max_workers: int | None,
) -> AlbumImportFailure | None:
    """Import one album, returning its failure (``None`` on success)."""
    try:
        result = _execute_plan(
            plan,
            gallery_dir,
            link_mode,
            dry_run,
            exiftool=exiftool,
            analyzer_factory=analyzer_factory,
            max_workers=max_workers,
        )
    except (ValueError, OSError) as exc:
        return AlbumImportFailure(source=plan.source, error=exc)
    return import_failure_of(plan.source, result)


def import_failure_of(
    source: Path, result: AlbumImportResult
) -> AlbumImportFailure | None:
    """The failure of an album that imported, ``None`` when it is complete.

    An album whose JPEGs or face detection partly failed is in the gallery,
    but reported as failed so the batch does not exit 0 on a partial result.
    """
    return (
        None
        if result.complete
        else AlbumImportFailure(
            source=source,
            jpeg_failures=result.jpeg_failures,
            face_failures=result.face_failures,
        )
    )


def run_batch_import(
    plans: list[AlbumPlan],
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, AlbumImportFailure | None], None] | None = None,
    max_workers: int | None = None,
    which: WhichFn = shutil.which,
) -> BatchImportResult:
    """Import/reimport multiple albums into a gallery.

    A shared exiftool and a memoized face analyzer factory are reused across
    albums (the model loads once, on the first album with images to detect).
    Calls ``on_start(name)`` before and ``on_end(name, failure_or_None)``
    after each album. A single album's failure is reported and the batch
    continues.
    """
    analyzer_factory = memoized_face_analyzer_factory()
    with exiftool_session(which=which) as exiftool:
        outcomes = [
            _notified(
                plan.source.name,
                lambda plan=plan: _import_one(
                    plan,
                    gallery_dir,
                    link_mode,
                    dry_run,
                    exiftool=exiftool,
                    analyzer_factory=analyzer_factory,
                    max_workers=max_workers,
                ),
                on_start=on_start,
                on_end=on_end,
            )
            for plan in plans
        ]
    return BatchImportResult(
        imported=tuple(
            plan.source for plan, o in zip(plans, outcomes, strict=True) if o is None
        ),
        failures=tuple(o for o in outcomes if o is not None),
    )


def _notified(
    name: str,
    action: Callable[[], AlbumImportFailure | None],
    *,
    on_start: Callable[[str], None] | None,
    on_end: Callable[[str, AlbumImportFailure | None], None] | None,
) -> AlbumImportFailure | None:
    """Run *action* between the start and end notifications for *name*."""
    if on_start is not None:
        on_start(name)
    outcome = action()
    if on_end is not None:
        on_end(name, outcome)
    return outcome
