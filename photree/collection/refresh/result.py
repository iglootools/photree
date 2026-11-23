"""The outcome of a collection refresh and the errors that stop one."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.naming import NamingIssue


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
    """
    An error encountered during collection refresh.

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
    """What a collection refresh changed, by name, and the errors that stopped it."""

    created: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()  # old name, then new name
    deleted: tuple[str, ...] = ()
    kept_directories: tuple[str, ...] = ()
    """Deleted collections whose directory was kept: it holds other files."""
    album_renames: tuple[tuple[str, str], ...] = ()  # old name, then new name
    errors: tuple[CollectionRefreshError, ...] = ()

    @property
    def success(self) -> bool:
        """Whether the refresh hit no error."""
        return len(self.errors) == 0
