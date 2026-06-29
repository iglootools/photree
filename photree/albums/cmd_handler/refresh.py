"""Batch refresh command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...album.faces.detect import memoized_face_analyzer_factory
from ...album.refresh import refresh_album_derived_data
from ...common.exif import try_start_exiftool


@dataclass(frozen=True)
class BatchRefreshResult:
    """Result of batch media metadata refresh."""

    refreshed: int
    failed_albums: list[Path] = field(default_factory=list)


def batch_refresh(
    albums: list[Path],
    *,
    dry_run: bool = False,
    force_browsable: bool = False,
    force_jpeg: bool = False,
    force_exif_cache: bool = False,
    redetect_faces: bool = False,
    refresh_face_thumbs: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None = None,
) -> BatchRefreshResult:
    """Refresh all derived data for multiple albums.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.

    A shared exiftool and a memoized face analyzer factory are reused across
    albums (the model loads once, on the first album with images to detect).
    """
    refreshed = 0
    failed_albums: list[Path] = []

    exiftool = try_start_exiftool()
    analyzer_factory = memoized_face_analyzer_factory()

    try:
        for album_dir in albums:
            album_name = display_fn(album_dir)
            if on_start:
                on_start(album_name)

            try:
                refresh_album_derived_data(
                    album_dir,
                    exiftool=exiftool,
                    analyzer_factory=analyzer_factory,
                    force_browsable=force_browsable,
                    force_jpeg=force_jpeg,
                    force_exif_cache=force_exif_cache,
                    redetect_faces=redetect_faces,
                    refresh_face_thumbs=refresh_face_thumbs,
                    dry_run=dry_run,
                )

                if on_end:
                    on_end(album_name, True, ())
                refreshed += 1
            except Exception:
                if on_end:
                    on_end(album_name, False, ())
                failed_albums.append(album_dir)
    finally:
        if exiftool is not None:
            exiftool.__exit__(None, None, None)

    return BatchRefreshResult(refreshed=refreshed, failed_albums=failed_albums)
