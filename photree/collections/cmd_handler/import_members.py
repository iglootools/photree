"""Batch import of collection selections into their collections."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache, partial
from pathlib import Path

from photree.collection.importer.import_members import (
    CollectionImportError,
    CollectionImportResult,
    import_collection_members,
)
from photree.collection.importer.resolve import GalleryIndex, scan_gallery
from photree.collection.importer.selection import has_selection
from photree.common.exif import ExifTagReader
from photree.common.progress import ItemEnd
from photree.foundation.metadata_io import InvalidMetadataError

type ImportFailureCause = CollectionImportError | InvalidMetadataError | OSError


@dataclass(frozen=True)
class CollectionImportOutcome:
    """
    One collection's import: its result, or the error that stopped it.

    Exactly one of ``result`` and ``error`` is set. A result can still be a
    failure, when a selection row or entry could not be used.
    """

    collection_dir: Path
    result: CollectionImportResult | None
    error: ImportFailureCause | None = None

    @property
    def success(self) -> bool:
        """Whether the collection's selection was imported (or would be)."""
        return self.result is not None and self.result.success

    @property
    def error_count(self) -> int:
        """How many reasons the import failed for: 0 on success."""
        match (self.result, self.error):
            case (CollectionImportResult() as result, _):
                return len(result.errors) + len(result.selection_errors)
            case _:
                return 1


@dataclass(frozen=True)
class BatchImportResult:
    """Each collection imported or attempted, and those skipped without a selection."""

    outcomes: tuple[CollectionImportOutcome, ...]
    skipped: tuple[Path, ...]

    @property
    def failures(self) -> tuple[CollectionImportOutcome, ...]:
        """Return the outcomes that failed, in order."""
        return tuple(o for o in self.outcomes if not o.success)


def _import_one(
    collection_dir: Path,
    gallery_index: Callable[[], GalleryIndex],
    *,
    dry_run: bool,
    exiftool: ExifTagReader | None,
) -> CollectionImportOutcome:
    """Import one collection; a failure is captured so the batch carries on."""
    try:
        result = import_collection_members(
            collection_dir,
            gallery_index,
            dry_run=dry_run,
            exiftool=exiftool,
        )
    except (CollectionImportError, InvalidMetadataError, OSError) as exc:
        return CollectionImportOutcome(collection_dir, None, exc)
    return CollectionImportOutcome(collection_dir, result)


def batch_import(
    candidates: Sequence[Path],
    gallery_dir: Path,
    *,
    dry_run: bool = False,
    exiftool: ExifTagReader | None = None,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_skipped: Callable[[str], None] | None = None,
    on_start: Callable[[str], None] | None = None,
    on_end: ItemEnd | None = None,
    scan: Callable[[Path], GalleryIndex] = scan_gallery,
) -> BatchImportResult:
    """
    Import the selection of every candidate collection that has one.

    A candidate without a selection is skipped (``on_skipped(name)``); the
    others are imported in order, between ``on_start(name)`` and
    ``on_end(name, success, error_labels)``. One collection failing never
    stops the batch.

    The gallery is scanned (*scan*) once, when the first collection gets
    to resolution, and that index serves every collection: an import never
    changes what it holds.
    """
    gallery_index = cache(partial(scan, gallery_dir))
    # has_selection is evaluated once per collection: it reads the CSV.
    selected = {d: has_selection(d) for d in candidates}
    skipped = tuple(d for d in candidates if not selected[d])
    for collection_dir in skipped:
        if on_skipped:
            on_skipped(display_fn(collection_dir))
    outcomes = tuple(
        _run_one(
            collection_dir,
            gallery_index,
            dry_run=dry_run,
            exiftool=exiftool,
            name=display_fn(collection_dir),
            on_start=on_start,
            on_end=on_end,
        )
        for collection_dir in candidates
        if selected[collection_dir]
    )
    return BatchImportResult(outcomes, skipped)


def _run_one(
    collection_dir: Path,
    gallery_index: Callable[[], GalleryIndex],
    *,
    dry_run: bool,
    exiftool: ExifTagReader | None,
    name: str,
    on_start: Callable[[str], None] | None,
    on_end: ItemEnd | None,
) -> CollectionImportOutcome:
    if on_start:
        on_start(name)
    outcome = _import_one(
        collection_dir,
        gallery_index,
        dry_run=dry_run,
        exiftool=exiftool,
    )
    if on_end:
        on_end(
            name,
            success=outcome.success,
            error_labels=(
                () if outcome.success else (f"{outcome.error_count} error(s)",)
            ),
        )
    return outcome
