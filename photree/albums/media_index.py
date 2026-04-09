"""Cross-album media index — duplicate media ID detection."""

from __future__ import annotations

import itertools
from pathlib import Path

from ..album.store.media_metadata import load_media_metadata


def find_duplicate_media_ids(
    albums: list[Path],
) -> dict[str, list[Path]]:
    """Find media UUIDs that appear in more than one album.

    Returns a dict mapping each duplicated media ID to the list of album
    paths that share it. Albums without ``.photree/media-ids/`` are
    silently skipped.
    """
    pairs: list[tuple[str, Path]] = []
    for album_dir in albums:
        metadata = load_media_metadata(album_dir)
        if metadata is None:
            continue
        for ms_meta in metadata.media_sources.values():
            for uuid in ms_meta.images:
                pairs.append((uuid, album_dir))
            for uuid in ms_meta.videos:
                pairs.append((uuid, album_dir))

    sorted_pairs = sorted(pairs, key=lambda t: t[0])
    grouped = {
        mid: [p for _, p in group]
        for mid, group in itertools.groupby(sorted_pairs, key=lambda t: t[0])
    }
    return {mid: paths for mid, paths in grouped.items() if len(paths) > 1}
