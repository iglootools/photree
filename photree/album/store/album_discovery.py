"""Finding the albums, and the would-be albums, under a directory."""

from pathlib import Path

from photree.album.store.media_sources_discovery import has_any_media_source
from photree.album.store.protocol import ALBUM_YAML
from photree.common.fs import matching_subdirectories, partition_subdirectories
from photree.foundation.layout import ALBUMS_DIR, PHOTREE_DIR


class AlbumSelectionError(ValueError):
    """Albums were selected both by base directory and by list, or by neither."""

    def __init__(self, parameters: tuple[str, str]) -> None:
        """Build the error from the two parameters exactly one of which is required."""
        self.parameters = parameters
        super().__init__(
            f"Exactly one of {parameters[0]} or {parameters[1]} must be provided",
        )


def is_album(directory: Path) -> bool:
    """
    Tell whether a directory is an album.

    A directory is an album if it contains ``.photree/album.yaml``
    **and** at least one media source (iOS or std).
    """
    return (directory / PHOTREE_DIR / ALBUM_YAML).is_file() and has_any_media_source(
        directory,
    )


def has_media_sources(directory: Path) -> bool:
    """Unlike :func:`is_album`, this does **not** require ``.photree/album.yaml``."""
    return has_any_media_source(directory)


def discover_albums(base_dir: Path) -> list[Path]:
    """
    Find the albums under *base_dir*.

    A directory is considered an album when it contains:

    1. A ``.photree/album.yaml`` file (album metadata), **and**
    2. At least one media source archive (``ios-{name}/`` or ``std-{name}/``)

    The *base_dir* itself is never returned as an album.
    """
    return matching_subdirectories(base_dir, is_album)


def discover_gallery_albums(gallery_dir: Path) -> list[Path]:
    """
    Find the albums of the gallery rooted at *gallery_dir*.

    A gallery's albums live under ``<gallery>/albums``; an album-like
    directory anywhere else in the gallery is not one of them. Every
    gallery-wide operation goes through here so that they all agree.
    """
    return discover_albums(gallery_dir / ALBUMS_DIR)


def discover_potential_albums(base_dir: Path) -> tuple[list[Path], list[Path]]:
    """
    Return ``(albums, skipped)``, the directories that could become albums and the rest.

    - *albums*: subdirectories with at least one media source. Recursion
      stops at each match.
    - *skipped*: subdirectories traversed during the walk that are not
      themselves albums (every level above a match plus non-matching
      leaves).

    Unlike :func:`discover_albums`, this does **not** require
    ``.photree/album.yaml`` — useful for commands that may create
    ``album.yaml`` themselves (init, import).

    The *base_dir* itself is never returned in either list.
    """
    return partition_subdirectories(base_dir, has_media_sources)
