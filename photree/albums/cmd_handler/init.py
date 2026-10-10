"""Batch init command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ...album.id import format_album_external_id, generate_album_id
from ...album.store.metadata import load_album_metadata, save_album_metadata
from ...album.store.protocol import AlbumMetadata
from . import (
    AlbumStepError,
    BatchFailure,
    OnEnd,
    OnStart,
    failures_of,
    run_album_step,
)


@dataclass(frozen=True)
class BatchInitResult:
    """Result of batch album initialization."""

    initialized: int
    failures: tuple[BatchFailure, ...] = ()

    @property
    def failed_albums(self) -> tuple[Path, ...]:
        return tuple(f.album_dir for f in self.failures)


def _init_one(album_dir: Path, *, dry_run: bool, new_id: Callable[[], str]) -> None:
    metadata = load_album_metadata(album_dir)
    if metadata is not None:
        raise AlbumStepError(
            f"already initialized: {format_album_external_id(metadata.id)}"
        )
    if not dry_run:
        save_album_metadata(album_dir, AlbumMetadata(id=new_id()))


def batch_init(
    albums: list[Path],
    *,
    dry_run: bool = False,
    new_id: Callable[[], str] = generate_album_id,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: OnStart = None,
    on_end: OnEnd = None,
) -> BatchInitResult:
    """Initialize album metadata for multiple albums.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.
    """
    outcomes = [
        run_album_step(
            album_dir,
            partial(_init_one, album_dir, dry_run=dry_run, new_id=new_id),
            name=display_fn(album_dir),
            on_start=on_start,
            on_end=on_end,
        )
        for album_dir in albums
    ]
    failures = failures_of(outcomes)
    return BatchInitResult(initialized=len(albums) - len(failures), failures=failures)
