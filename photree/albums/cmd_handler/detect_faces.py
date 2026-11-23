"""Batch face detection."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from photree.album.faces.detect import (
    FaceAnalyzerFactory,
    memoized_face_analyzer_factory,
)
from photree.album.faces.refresh import refresh_face_data
from photree.albums.cmd_handler import (
    AlbumStepError,
    BatchFailure,
    OnEnd,
    OnStart,
    failures_of,
    run_album_step,
)


@dataclass(frozen=True)
class BatchDetectFacesResult:
    """Result of batch face detection: how many albums succeeded, and failures."""

    succeeded: int
    failures: tuple[BatchFailure, ...] = ()


def _detect_one(
    album_dir: Path,
    *,
    analyzer_factory: FaceAnalyzerFactory,
    redetect: bool,
    refresh_thumbs: bool,
    dry_run: bool,
    max_workers: int | None,
) -> None:
    result = refresh_face_data(
        album_dir,
        analyzer_factory=analyzer_factory,
        redetect=redetect,
        refresh_thumbs=refresh_thumbs,
        dry_run=dry_run,
        max_workers=max_workers,
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
    max_workers: int | None = None,
) -> BatchDetectFacesResult:
    """
    Run face detection on multiple albums with one shared (lazy) model.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.
    """
    detect = partial(
        _detect_one,
        analyzer_factory=memoized_face_analyzer_factory(),
        redetect=redetect,
        refresh_thumbs=refresh_thumbs,
        dry_run=dry_run,
        max_workers=max_workers,
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
        succeeded=len(albums) - len(failures),
        failures=failures,
    )
