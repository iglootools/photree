"""Result and error types of a collection refresh."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...album.naming import (
    NamingIssue,
)


class CollectionRefreshErrorKind(StrEnum):
    """Why a collection refresh stopped."""

    ALBUM_NAMING = "album-naming"
    """``path``: album whose name breaks the convention (``naming_issues``)."""

    ALBUM_MISSING_METADATA = "album-missing-metadata"
    """``path``: album without a readable ``.photree/album.yaml``."""

    COLLECTION_UNREADABLE_METADATA = "collection-unreadable-metadata"
    """``path``: collection whose ``collection.yaml`` cannot be read."""

    DATE_COLLISION = "date-collision"
    """``name``: the date; ``album_names``: the colliding albums."""

    ALBUM_RENAME_CONFLICT = "album-rename-conflict"
    """``path``: album; ``target``: title-sync name already taken."""

    COLLECTION_TARGET_EXISTS = "collection-target-exists"
    """``path``: collection being renamed (``None`` on create); ``target``."""

    SERIES_NAME_CONFLICT = "series-name-conflict"
    """``name``: implicit collection name claimed by two album series runs."""


@dataclass(frozen=True)
class CollectionRefreshError:
    """An error encountered during collection refresh.

    Which fields are set depends on :attr:`kind` (see
    :class:`CollectionRefreshErrorKind`). Paths are absolute; the CLI renders
    them relative to the working directory.
    """

    kind: CollectionRefreshErrorKind
    path: Path | None = None
    target: Path | None = None
    name: str | None = None
    naming_issues: tuple[NamingIssue, ...] = ()
    album_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionRefreshResult:
    """Result of a collection refresh run."""

    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()  # (old_name, new_name)
    deleted: tuple[str, ...] = ()
    album_renames: tuple[tuple[str, str], ...] = ()  # (old_name, new_name)
    errors: tuple[CollectionRefreshError, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0
