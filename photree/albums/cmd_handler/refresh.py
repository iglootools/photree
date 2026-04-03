"""Batch refresh command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...album.refresh import refresh_media_metadata


@dataclass(frozen=True)
class BatchRefreshResult:
    """Result of batch media metadata refresh."""

    refreshed: int
    failed_albums: list[Path] = field(default_factory=list)


def batch_refresh(
    albums: list[Path],
    *,
    dry_run: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None = None,
) -> BatchRefreshResult:
    """Refresh media metadata for multiple albums.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.
    """
    refreshed = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = display_fn(album_dir)
        if on_start:
            on_start(album_name)

        try:
            refresh_media_metadata(album_dir, dry_run=dry_run)

            if on_end:
                on_end(album_name, True, ())
            refreshed += 1
        except Exception:
            if on_end:
                on_end(album_name, False, ())
            failed_albums.append(album_dir)

    return BatchRefreshResult(refreshed=refreshed, failed_albums=failed_albums)
