"""Gallery import command handlers (single and batch)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...album.faces.detect import memoized_face_analyzer_factory
from ...common.exif import try_start_exiftool
from ...fsprotocol import LinkMode
from .. import importer as gallery_importer
from ..importer import AlbumImportResult
from ..import_plan import AlbumPlan, ImportAction


def _execute_plan(
    plan: AlbumPlan,
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    exiftool=None,
    analyzer_factory=None,
    max_workers: int | None = None,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
) -> AlbumImportResult:
    """Dispatch a single plan to import or reimport."""
    if plan.action is ImportAction.REIMPORT:
        assert plan.existing is not None  # REIMPORT always carries the existing dir
        return gallery_importer.reimport_album(
            source_dir=plan.source,
            gallery_dir=gallery_dir,
            existing_dir=plan.existing,
            link_mode=link_mode,
            dry_run=dry_run,
            on_stage_start=on_stage_start,
            on_stage_end=on_stage_end,
            max_workers=max_workers,
            exiftool=exiftool,
            analyzer_factory=analyzer_factory,
        )
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


def run_single_import(
    plan: AlbumPlan,
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
    max_workers: int | None = None,
) -> AlbumImportResult:
    """Execute a single album import/reimport with optional stage callbacks.

    Creates a shared exiftool and injects a memoized face analyzer factory
    (loaded lazily, only if a source has images to detect).
    Raises :class:`ValueError` on import errors.
    """
    exiftool = try_start_exiftool()

    try:
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
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)


@dataclass(frozen=True)
class BatchImportResult:
    """Result of batch gallery import."""

    imported: int
    failed_albums: list[Path] = field(default_factory=list)


def run_batch_import(
    plans: list[AlbumPlan],
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None = None,
    max_workers: int | None = None,
) -> BatchImportResult:
    """Import/reimport multiple albums into a gallery.

    A shared exiftool and a memoized face analyzer factory are reused across
    albums (the model loads once, on the first album with images to detect).
    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album. A single
    album's failure is reported and the batch continues.
    """
    imported = 0
    failed: list[Path] = []

    exiftool = try_start_exiftool()
    analyzer_factory = memoized_face_analyzer_factory()

    try:
        for plan in plans:
            album_name = plan.source.name
            if on_start:
                on_start(album_name)
            try:
                _execute_plan(
                    plan,
                    gallery_dir,
                    link_mode,
                    dry_run,
                    exiftool=exiftool,
                    analyzer_factory=analyzer_factory,
                    max_workers=max_workers,
                )
                if on_end:
                    on_end(album_name, True, ())
                imported += 1
            except (ValueError, OSError) as exc:
                if on_end:
                    on_end(album_name, False, (str(exc)[:60],))
                failed.append(plan.source)
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)

    return BatchImportResult(imported=imported, failed_albums=failed)
