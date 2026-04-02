"""Validate album before gallery import."""

from __future__ import annotations

from pathlib import Path

from ...album.naming import (
    AlbumNamingResult,
    check_album_naming,
    parse_album_name,
)
from ...album.store.fs import load_album_metadata
from ...album.store.protocol import format_album_external_id
from .. import AlbumIndex
from ..importer import compute_target_dir


class ImportValidationError(ValueError):
    """Raised when an album fails pre-import validation."""


class DuplicateAlbumIdError(ImportValidationError):
    """Album ID already exists in gallery."""

    def __init__(self, source: Path, existing: Path, album_id: str) -> None:
        self.source = source
        self.existing = existing
        self.album_id = album_id
        super().__init__(
            f"Cannot import — album ID already exists in gallery:\n"
            f"  source: {source}\n"
            f"  existing: {existing}\n"
            f"  id: {format_album_external_id(album_id)}"
        )


class NamingValidationError(ImportValidationError):
    """Album name does not follow naming conventions."""

    def __init__(self, naming_result: AlbumNamingResult) -> None:
        self.naming_result = naming_result
        super().__init__(
            "Album name does not follow naming conventions. "
            "Rename the album directory before importing."
        )


class TargetExistsError(ImportValidationError):
    """Target directory already exists in gallery."""

    def __init__(self, target: Path) -> None:
        self.target = target
        super().__init__(
            f"Target already exists: {target}\n"
            "Cannot import — an album with the same name is already in the gallery."
        )


def validate_single_import(
    album_dir: Path,
    index: AlbumIndex,
    gallery_dir: Path,
) -> None:
    """Validate a single album before import.

    Checks source album ID uniqueness, naming conventions, and that the
    target directory does not already exist.

    Raises :class:`ImportValidationError` subclasses on failure.
    """
    # Check source album ID uniqueness against gallery
    source_meta = load_album_metadata(album_dir)
    if source_meta is not None and source_meta.id in index.id_to_path:
        existing = index.id_to_path[source_meta.id]
        raise DuplicateAlbumIdError(album_dir, existing, source_meta.id)

    # Validate album name
    naming_issues = check_album_naming(album_dir.name)
    if naming_issues:
        parsed = parse_album_name(album_dir.name)
        naming_result = AlbumNamingResult(
            parsed=parsed, issues=naming_issues, exif_check=None
        )
        raise NamingValidationError(naming_result)

    # Check target doesn't exist
    target = compute_target_dir(gallery_dir, album_dir.name)
    if target.exists():
        raise TargetExistsError(target)
