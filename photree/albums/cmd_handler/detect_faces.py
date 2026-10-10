"""Batch face-detection command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ...album.faces.detect import FaceAnalyzerFactory, memoized_face_analyzer_factory
from ...album.faces.refresh import refresh_face_data
from . import (
    AlbumStepError,
    BatchFailure,
    OnEnd,
    OnStart,
    failures_of,
    run_album_step,
)


@dataclass(frozen=True)
class BatchDetectFacesResult:
    """Result of batch face detection."""

    succeeded: int
    failures: tuple[BatchFailure, ...] = ()

    @property
    def failed_albums(self) -> tuple[Path, ...]:
        return tuple(f.album_dir for f in self.failures)


def _detect_one(
    album_dir: Path,
    *,
    analyzer_factory: FaceAnalyzerFactory,
    redetect: bool,
    refresh_thumbs: bool,
    dry_run: bool,
) -> None:
    result = refresh_face_data(
        album_dir,
        analyzer_factory=analyzer_factory,
        redetect=redetect,
        refresh_thumbs=refresh_thumbs,
        dry_run=dry_run,
    )
    # Per-image failures leave the album's face data incomplete: a failure.
    if result.failures:
        labels = tuple(
            f"{ms}/{f.key} ({f.stage}): {f.reason}" for ms, f in result.failures
        )
        raise AlbumStepError("; ".join(labels), labels)


def batch_detect_faces(
    albums: list[Path],
    *,
    redetect: bool = False,
    refresh_thumbs: bool = False,
    dry_run: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: OnStart = None,
    on_end: OnEnd = None,
) -> BatchDetectFacesResult:
    """Run face detection on multiple albums with one shared (lazy) model.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.
    """
    detect = partial(
        _detect_one,
        analyzer_factory=memoized_face_analyzer_factory(),
        redetect=redetect,
        refresh_thumbs=refresh_thumbs,
        dry_run=dry_run,
    )
    outcomes = [
        run_album_step(
            album_dir,
            partial(detect, album_dir),
            name=display_fn(album_dir),
            on_start=on_start,
            on_end=on_end,
        )
        for album_dir in albums
    ]
    failures = failures_of(outcomes)
    return BatchDetectFacesResult(
        succeeded=len(albums) - len(failures), failures=failures
    )
