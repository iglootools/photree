"""Archive collisions: incoming media whose key already exists in the target source.

Both importers (iOS by image number, std by filename stem) refuse to copy a
key that the target archive already holds. The check runs before any mutation
— during validation and again at the start of
:func:`photree.album.importer.album_import.run_import` — so a collision in one
media source can never leave another source half-imported.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..store.media_source import MediaSource


@dataclass(frozen=True)
class ArchiveCollision:
    """Incoming keys that already exist in *media_source*'s archive.

    Keys are image numbers for iOS sources and filename stems for std sources.
    """

    media_source: MediaSource
    keys: tuple[str, ...]


class ImportCollisionError(ValueError):
    """Raised when an import would overwrite keys already in the archive."""

    def __init__(self, media_source: MediaSource, keys: tuple[str, ...]) -> None:
        self.media_source = media_source
        self.keys = keys
        super().__init__(
            f"import would conflict with {len(keys)} existing key(s) "
            f"in media source '{media_source.name}'"
        )

    @classmethod
    def from_collision(cls, collision: ArchiveCollision) -> ImportCollisionError:
        return cls(collision.media_source, collision.keys)
