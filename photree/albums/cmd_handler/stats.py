"""Batch stats command handler."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...album import stats as album_stats


def batch_stats(
    albums: list[Path],
    *,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool], None] | None = None,
) -> album_stats.GalleryStats:
    """Compute aggregated stats for multiple albums.

    Calls ``on_start(name)`` before and ``on_end(name, success)`` after
    each album.
    """
    album_stats_list: list[album_stats.AlbumStats] = []
    for album_dir in albums:
        album_name = display_fn(album_dir)
        if on_start:
            on_start(album_name)
        stats = album_stats.compute_album_stats(album_dir)
        album_stats_list.append(stats)
        if on_end:
            on_end(album_name, True)

    return album_stats.gallery_stats_from_album_stats(album_stats_list)
