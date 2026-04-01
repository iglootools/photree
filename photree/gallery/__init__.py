"""Gallery-level operations: album ID indexing, path lookups, and import."""

from .batch_rename import RenameAction, plan_renames_from_csv
from .index import (
    AlbumIndex,
    MissingAlbumIdError,
    build_album_id_to_path_index,
    find_duplicate_album_ids,
    resolve_album_path_by_id,
)

__all__ = [
    "AlbumIndex",
    "MissingAlbumIdError",
    "RenameAction",
    "build_album_id_to_path_index",
    "find_duplicate_album_ids",
    "plan_renames_from_csv",
    "resolve_album_path_by_id",
]
