"""Multi-album indexing — ID→path mapping and duplicate detection."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path

from ..album.store.metadata import load_album_metadata


@dataclass(frozen=True)
class AlbumIndex:
    """In-memory mapping of album IDs to their filesystem paths."""

    id_to_path: dict[str, Path]
    """Internal UUID → album path (first occurrence when duplicates exist)."""

    duplicates: dict[str, tuple[Path, ...]]
    """IDs that map to more than one album path."""


@dataclass(frozen=True)
class MissingAlbumIdError(Exception):
    """Raised when discovered albums lack a ``.photree/album.yaml`` ID."""

    albums: tuple[Path, ...]


def build_album_index(albums: list[Path]) -> AlbumIndex:
    """Build an ID→path index from a list of album paths.

    Raises :class:`MissingAlbumIdError` if any album lacks an ID.
    """
    missing = tuple(
        album_dir for album_dir in albums if load_album_metadata(album_dir) is None
    )
    if missing:
        raise MissingAlbumIdError(albums=missing)

    pairs = [
        (meta.id, album_dir)
        for album_dir in albums
        if (meta := load_album_metadata(album_dir)) is not None
    ]

    sorted_pairs = sorted(pairs, key=lambda t: t[0])
    grouped = {
        aid: tuple(p for _, p in group)
        for aid, group in itertools.groupby(sorted_pairs, key=lambda t: t[0])
    }

    return AlbumIndex(
        id_to_path={aid: paths[0] for aid, paths in grouped.items()},
        duplicates={aid: paths for aid, paths in grouped.items() if len(paths) > 1},
    )


def find_duplicate_album_ids(
    albums: list[Path],
) -> dict[str, list[Path]]:
    """Find albums that share the same ID.

    Returns a dict mapping each duplicated album ID to the list of paths
    that share it. Albums without metadata are silently skipped.
    """
    pairs = [
        (meta.id, album_dir)
        for album_dir in albums
        if (meta := load_album_metadata(album_dir)) is not None
    ]
    sorted_pairs = sorted(pairs, key=lambda t: t[0])
    grouped = {
        aid: [p for _, p in group]
        for aid, group in itertools.groupby(sorted_pairs, key=lambda t: t[0])
    }
    return {aid: paths for aid, paths in grouped.items() if len(paths) > 1}


def resolve_album_path_by_id(index: dict[str, Path], album_id: str) -> Path:
    """Look up an album path by internal UUID.

    Raises :class:`KeyError` when *album_id* is not in the index.
    """
    try:
        return index[album_id]
    except KeyError:
        raise KeyError(f"Album ID not found in gallery index: {album_id}")
