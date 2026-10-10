"""Core import logic — resolve and merge members into a collection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..store.metadata import load_collection_metadata, save_collection_metadata
from ..store.protocol import CollectionLifecycle, CollectionMembers, CollectionMetadata
from .resolve import (
    ResolutionError,
    ResolutionWarning,
    ResolvedMembers,
    resolve_entries,
)
from .selection import SELECTION_CSV, SELECTION_DIR, SelectionError, read_selection


class CollectionImportErrorKind(StrEnum):
    """Why a collection cannot be imported into at all."""

    NO_METADATA = "no-metadata"
    IMPLICIT_COLLECTION = "implicit-collection"
    SMART_COLLECTION = "smart-collection"
    NO_SELECTION = "no-selection"


class CollectionImportError(Exception):
    """The collection cannot be imported into.

    Structured (kind + path) so the CLI renders the message with
    ``display_path`` and a suggestion; see
    :func:`photree.collection.importer.output.format_import_error`.
    """

    def __init__(self, kind: CollectionImportErrorKind, collection_dir: Path) -> None:
        self.kind = kind
        self.collection_dir = collection_dir
        super().__init__(f"{kind}: {collection_dir}")


@dataclass(frozen=True)
class CollectionImportResult:
    """Result of importing members into a single collection."""

    collection_dir: Path
    collection_id: str
    members: ResolvedMembers
    errors: tuple[ResolutionError, ...]
    warnings: tuple[ResolutionWarning, ...] = ()
    selection_errors: tuple[SelectionError, ...] = ()

    @property
    def success(self) -> bool:
        return not self.errors and not self.selection_errors


_EMPTY_MEMBERS = ResolvedMembers(albums=(), collections=(), images=(), videos=())


def _merge_ids(existing: list[str], new: tuple[str, ...]) -> list[str]:
    """Merge new IDs into existing list, preserving order and avoiding duplicates."""
    seen = set(existing)
    return [
        *existing,
        *(item for item in new if item not in seen),
    ]


def _cleanup_selection(collection_dir: Path) -> None:
    """Remove selection sources after successful import."""
    selection_dir = collection_dir / SELECTION_DIR
    if selection_dir.is_dir():
        for f in selection_dir.iterdir():
            if f.is_file():
                f.unlink()
        if not any(selection_dir.iterdir()):
            selection_dir.rmdir()

    csv_path = collection_dir / SELECTION_CSV
    if csv_path.is_file():
        csv_path.unlink()


def _load_importable(collection_dir: Path) -> CollectionMetadata:
    """Load the collection's metadata, refusing collections that cannot import."""
    metadata = load_collection_metadata(collection_dir)
    match metadata:
        case None:
            raise CollectionImportError(
                CollectionImportErrorKind.NO_METADATA, collection_dir
            )
        case CollectionMetadata(lifecycle=CollectionLifecycle.IMPLICIT):
            raise CollectionImportError(
                CollectionImportErrorKind.IMPLICIT_COLLECTION, collection_dir
            )
        case CollectionMetadata(members=CollectionMembers.SMART):
            raise CollectionImportError(
                CollectionImportErrorKind.SMART_COLLECTION, collection_dir
            )
        case _:
            return metadata


def _merged_metadata(
    metadata: CollectionMetadata, members: ResolvedMembers
) -> CollectionMetadata:
    return CollectionMetadata(
        id=metadata.id,
        members=metadata.members,
        lifecycle=metadata.lifecycle,
        strategy=metadata.strategy,
        albums=_merge_ids(metadata.albums, members.albums),
        collections=_merge_ids(metadata.collections, members.collections),
        images=_merge_ids(metadata.images, members.images),
        videos=_merge_ids(metadata.videos, members.videos),
    )


def import_collection_members(
    collection_dir: Path,
    gallery_dir: Path,
    *,
    dry_run: bool = False,
    exiftool: ExifToolHelper | None = None,
) -> CollectionImportResult:
    """Resolve selection entries and merge into collection metadata.

    Returns the result with resolved members or errors. On success (and
    not dry_run), saves updated metadata and cleans up selection sources.
    Unusable selection rows (e.g. an unparseable date) fail the import
    before anything is resolved or written.

    Raises :class:`CollectionImportError` when the collection has no
    metadata, cannot be imported into (implicit/smart), or has no
    selection entries.
    """
    metadata = _load_importable(collection_dir)

    sources = read_selection(collection_dir, exiftool=exiftool)
    if sources.errors:
        return CollectionImportResult(
            collection_dir,
            metadata.id,
            _EMPTY_MEMBERS,
            errors=(),
            selection_errors=sources.errors,
        )
    if not sources.merged:
        raise CollectionImportError(
            CollectionImportErrorKind.NO_SELECTION, collection_dir
        )

    result = resolve_entries(sources.merged, gallery_dir)
    if result.success and not dry_run:
        save_collection_metadata(
            collection_dir, _merged_metadata(metadata, result.members)
        )
        _cleanup_selection(collection_dir)

    return CollectionImportResult(
        collection_dir=collection_dir,
        collection_id=metadata.id,
        members=result.members,
        errors=result.errors,
        warnings=result.warnings,
    )
