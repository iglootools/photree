"""Batch refresh command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...album.faces.detect import FaceAnalyzerFactory, memoized_face_analyzer_factory
from ...album.faces.failures import format_face_failures
from ...album.refresh import AlbumRefreshResult, refresh_album_derived_data
from ...common.exif import exiftool_session
from . import (
    AlbumStepError,
    BatchFailure,
    OnEnd,
    OnStart,
    failures_of,
    run_album_step,
)


@dataclass(frozen=True)
class BatchRefreshResult:
    """Result of batch media metadata refresh."""

    refreshed: int
    failures: tuple[BatchFailure, ...] = ()

    @property
    def failed_albums(self) -> tuple[Path, ...]:
        return tuple(f.album_dir for f in self.failures)


@dataclass(frozen=True)
class _RefreshOptions:
    dry_run: bool
    force_browsable: bool
    force_jpeg: bool
    force_exif_cache: bool
    redetect_faces: bool
    refresh_face_thumbs: bool


def _refresh_one(
    album_dir: Path,
    opts: _RefreshOptions,
    exiftool: ExifToolHelper | None,
    analyzer_factory: FaceAnalyzerFactory,
) -> None:
    result = refresh_album_derived_data(
        album_dir,
        exiftool=exiftool,
        analyzer_factory=analyzer_factory,
        force_browsable=opts.force_browsable,
        force_jpeg=opts.force_jpeg,
        force_exif_cache=opts.force_exif_cache,
        redetect_faces=opts.redetect_faces,
        refresh_face_thumbs=opts.refresh_face_thumbs,
        dry_run=opts.dry_run,
    )
    # A JPEG that failed to convert leaves a gap in {name}-jpg/, and an image
    # whose face detection failed is missing from clustering. The album
    # refreshed, but not completely — report it as failed so the run does not
    # exit 0 on a partial result.
    if not result.success:
        raise _partial_refresh_error(result)


def _partial_refresh_error(result: AlbumRefreshResult) -> AlbumStepError:
    """One failure carrying every JPEG and face-detection problem as labels."""
    jpeg = tuple(
        f"{source}/{failure.filename}: {failure.reason}"
        for source, failure in result.jpeg_failures
    )
    faces = tuple(format_face_failures(result.face_failures))
    reason = "; ".join(
        [
            *([f"jpeg conversion failed: {'; '.join(jpeg)}"] if jpeg else []),
            *([f"face detection failed: {'; '.join(faces)}"] if faces else []),
        ]
    )
    return AlbumStepError(reason, (*jpeg, *faces))


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
    on_start: OnStart = None,
    on_end: OnEnd = None,
) -> BatchRefreshResult:
    """Refresh all derived data for multiple albums.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.

    A shared exiftool and a memoized face analyzer factory are reused across
    albums (the model loads once, on the first album with images to detect).
    """
    opts = _RefreshOptions(
        dry_run,
        force_browsable,
        force_jpeg,
        force_exif_cache,
        redetect_faces,
        refresh_face_thumbs,
    )
    analyzer_factory = memoized_face_analyzer_factory()
    with exiftool_session() as exiftool:
        outcomes = [
            run_album_step(
                album_dir,
                partial(_refresh_one, album_dir, opts, exiftool, analyzer_factory),
                name=display_fn(album_dir),
                on_start=on_start,
                on_end=on_end,
            )
            for album_dir in albums
        ]
    failures = failures_of(outcomes)
    return BatchRefreshResult(refreshed=len(albums) - len(failures), failures=failures)
