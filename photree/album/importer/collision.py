"""
Collisions an import refuses: with the target archive's keys, or its name.

Both importers (iOS by image number, std by filename stem) refuse to copy a
key that the target archive already holds. An import also refuses to give a
media source name both an iOS and a std archive, which would share the same
browsable directories and media IDs. The checks run before any mutation —
during validation and again at the start of
:func:`photree.album.importer.album_import.run_import` — so a collision in one
media source can never leave another source half-imported.
"""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.store.media_source import (
    MediaSource,
    MediaSourceType,
    ios_media_source,
    std_media_source,
)
from photree.album.store.media_sources_discovery import has_media_source_archive


@dataclass(frozen=True)
class ArchiveCollision:
    """
    Incoming keys that already exist in *media_source*'s archive.

    Keys are image numbers for iOS sources and filename stems for std sources.
    """

    media_source: MediaSource
    keys: tuple[str, ...]


class ImportCollisionError(ValueError):
    """Raised when an import would copy keys that *media_source*'s archive holds."""

    def __init__(self, media_source: MediaSource, keys: tuple[str, ...]) -> None:
        """Build the error from the target media source and its colliding keys."""
        self.media_source = media_source
        self.keys = keys
        super().__init__(
            f"import would conflict with {len(keys)} existing key(s) "
            f"in media source '{media_source.name}'",
        )

    @classmethod
    def from_collision(cls, collision: ArchiveCollision) -> ImportCollisionError:
        """Build the error from a collision found during validation."""
        return cls(collision.media_source, collision.keys)


class MediaSourceClashErrorKind(StrEnum):
    """What already claims an import task's media source name for the other type."""

    # The album holds the other type's archive under the same name.
    EXISTING_ARCHIVE = "existing-archive"
    # The other type is staged under the same name too.
    STAGED = "staged"


@dataclass(frozen=True)
class MediaSourceClash:
    """
    Importing into *media_source* would back its name with an iOS and a std archive.

    The two archives would share the same browsable directories and media
    IDs, and every later album command would refuse the album.
    """

    media_source: MediaSource
    kind: MediaSourceClashErrorKind

    @property
    def other(self) -> MediaSource:
        """Return the media source of the other type with the same name."""
        return other_type(self.media_source)


class MediaSourceClashError(ValueError):
    """Raised when an import would back a media source name with both types."""

    def __init__(self, clash: MediaSourceClash) -> None:
        """Build the error from the clash found."""
        self.clash = clash
        super().__init__(
            f"media source '{clash.media_source.name}' would have both an iOS "
            f"and a std archive ({clash.kind})",
        )


def other_type(ms: MediaSource) -> MediaSource:
    """Return the media source of the other type with *ms*'s name."""
    match ms.media_source_type:
        case MediaSourceType.IOS:
            return std_media_source(ms.name)
        case MediaSourceType.STD:
            return ios_media_source(ms.name)


def find_media_source_clash(
    album_dir: Path,
    ms: MediaSource,
    staged: Collection[MediaSource],
) -> MediaSourceClash | None:
    """
    Find what would give *ms*'s name a second archive of the other type.

    *staged* holds the media sources of every import task of the album. An
    archive already on disk is reported before a staged one.
    """
    other = other_type(ms)
    match (has_media_source_archive(album_dir, other), other in staged):
        case (True, _):
            return MediaSourceClash(ms, MediaSourceClashErrorKind.EXISTING_ARCHIVE)
        case (False, True):
            return MediaSourceClash(ms, MediaSourceClashErrorKind.STAGED)
        case _:
            return None
