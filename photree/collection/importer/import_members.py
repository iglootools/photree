"""Core import logic — resolve and merge members into a collection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ..store.metadata import load_collection_metadata, save_collection_metadata
from ..store.protocol import CollectionKind, CollectionLifecycle, CollectionMetadata
from .resolve import (
    ResolutionError,
    ResolutionWarning,
    ResolvedMembers,
    resolve_entries,
)
from .selection import SELECTION_CSV, SELECTION_DIR, read_selection


@dataclass(frozen=True)
class CollectionImportResult:
    """Result of importing members into a single collection."""

    collection_dir: Path
    members: ResolvedMembers
    errors: tuple[ResolutionError, ...]
    warnings: tuple[ResolutionWarning, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


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

    Raises ``FileNotFoundError`` if collection metadata is missing.
    Raises ``ValueError`` if no selection entries found.
    """
    metadata = load_collection_metadata(collection_dir)
    if metadata is None:
        raise FileNotFoundError(f"No collection metadata found in {collection_dir}")

    if metadata.lifecycle == CollectionLifecycle.IMPLICIT:
        raise ValueError(
            "Cannot import into an implicit collection — members are managed "
            "by 'gallery refresh' via album series detection."
        )

    if metadata.kind == CollectionKind.SMART:
        raise ValueError(
            "Cannot import into a smart collection — members are managed "
            "automatically by 'gallery refresh'. Use 'collection metadata set "
            "--kind manual' to convert first."
        )

    sources = read_selection(collection_dir, exiftool=exiftool)
    if not sources.merged:
        raise ValueError(
            f"No selection entries found in {SELECTION_DIR}/ or {SELECTION_CSV}"
        )

    result = resolve_entries(sources.merged, gallery_dir)

    if not result.success:
        return CollectionImportResult(
            collection_dir=collection_dir,
            members=result.members,
            errors=result.errors,
            warnings=result.warnings,
        )

    if not dry_run:
        members = result.members
        updated = CollectionMetadata(
            id=metadata.id,
            kind=metadata.kind,
            lifecycle=metadata.lifecycle,
            albums=_merge_ids(metadata.albums, members.albums),
            collections=_merge_ids(metadata.collections, members.collections),
            images=_merge_ids(metadata.images, members.images),
            videos=_merge_ids(metadata.videos, members.videos),
        )
        save_collection_metadata(collection_dir, updated)
        _cleanup_selection(collection_dir)

    return CollectionImportResult(
        collection_dir=collection_dir,
        members=result.members,
        errors=(),
        warnings=result.warnings,
    )
