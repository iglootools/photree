"""Batch refresh command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from insightface.app import FaceAnalysis

from ...album.faces.detect import create_face_analyzer
from ...album.faces.refresh import refresh_face_data
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
    redetect_faces: bool = False,
    regenerate_face_thumbs: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None = None,
) -> BatchRefreshResult:
    """Refresh media metadata and face data for multiple albums.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.

    A single :class:`FaceAnalysis` instance is shared across albums
    to avoid reloading the model (~500 MB) for each album.
    """
    refreshed = 0
    failed_albums: list[Path] = []

    # Create shared face analyzer once for all albums
    face_analyzer: FaceAnalysis | None = None

    for album_dir in albums:
        album_name = display_fn(album_dir)
        if on_start:
            on_start(album_name)

        try:
            refresh_media_metadata(album_dir, dry_run=dry_run)

            # Lazy-init face analyzer on first use
            if face_analyzer is None:
                face_analyzer = create_face_analyzer()

            refresh_face_data(
                album_dir,
                face_analyzer=face_analyzer,
                redetect=redetect_faces,
                regenerate_thumbs=regenerate_face_thumbs,
                dry_run=dry_run,
            )

            if on_end:
                on_end(album_name, True, ())
            refreshed += 1
        except Exception:
            if on_end:
                on_end(album_name, False, ())
            failed_albums.append(album_dir)

    return BatchRefreshResult(refreshed=refreshed, failed_albums=failed_albums)
