"""Album discovery — find album directories by scanning for metadata and media sources."""

from __future__ import annotations

from pathlib import Path

from ...common.fs import matching_subdirectories
from ...fsprotocol import PHOTREE_DIR
from .media_sources_discovery import discover_media_sources
from .protocol import ALBUM_YAML


def is_album(directory: Path) -> bool:
    """Check if a directory is a photree album.

    A directory is an album if it contains ``.photree/album.yaml``
    **and** at least one media source (iOS or std).
    """
    return (directory / PHOTREE_DIR / ALBUM_YAML).is_file() and bool(
        discover_media_sources(directory)
    )


def has_media_sources(directory: Path) -> bool:
    """Check if a directory has at least one media source.

    Unlike :func:`is_album`, this does **not** require ``.photree/album.yaml``.
    """
    return bool(discover_media_sources(directory))


def discover_albums(base_dir: Path) -> list[Path]:
    """Recursively discover album directories under *base_dir*.

    A directory is considered an album when it contains:
    1. A ``.photree/album.yaml`` file (album metadata), **and**
    2. At least one media source (``ios-{name}/`` or ``{name}-img/``/``{name}-vid/``)

    The *base_dir* itself is never returned as an album.
    """
    return matching_subdirectories(base_dir, is_album)


def discover_potential_albums(base_dir: Path) -> list[Path]:
    """Recursively discover directories with media sources under *base_dir*.

    Unlike :func:`discover_albums`, this does **not** require
    ``.photree/album.yaml`` — it finds any directory with at least one
    media source. Useful for ``init`` commands that create ``album.yaml``.

    The *base_dir* itself is never returned.
    """
    return matching_subdirectories(base_dir, has_media_sources)
