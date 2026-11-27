"""Batch initialization of album metadata."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from photree.album.id import format_album_external_id, generate_album_id
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.albums.cmd_handler import (
    BatchFailure,
    OnEnd,
    OnStart,
    StepOutcome,
    failures_of,
    run_album_step,
)

type OnAlreadyInitialized = Callable[[str, str], None] | None
"""Called with an album's display name and its existing external ID."""


@dataclass(frozen=True)
class BatchInitResult:
    """
    Result of batch init.

    ``initialized`` counts the albums given an ID (or that would be, in a dry
    run), ``skipped`` those that already had one, and ``failures`` the rest.
    """

    initialized: int
    skipped: int = 0
    failures: tuple[BatchFailure, ...] = ()


def _init_one(
    album_dir: Path,
    *,
    dry_run: bool,
    new_id: Callable[[], str],
) -> str | None:
    """Give *album_dir* an ID, or return the external ID it already has."""
    metadata = load_album_metadata(album_dir)
    if metadata is not None:
        return format_album_external_id(metadata.id)
    if not dry_run:
        save_album_metadata(album_dir, AlbumMetadata(id=new_id()))
    return None


def _init_album(
    album_dir: Path,
    *,
    name: str,
    dry_run: bool,
    new_id: Callable[[], str],
    on_start: OnStart,
    on_end: OnEnd,
    on_already_initialized: OnAlreadyInitialized,
) -> StepOutcome[str | None]:
    """
    Initialize one album and report how it ended.

    The end is reported here rather than by :func:`run_album_step`, which
    would report an album left alone as a success.
    """
    outcome = run_album_step(
        album_dir,
        partial(_init_one, album_dir, dry_run=dry_run, new_id=new_id),
        name=name,
        on_start=on_start,
    )
    match outcome:
        case StepOutcome(failure=BatchFailure(reason=reason)):
            if on_end:
                on_end(name, success=False, error_labels=(reason,))
        case StepOutcome(value=str() as existing_id):
            if on_already_initialized:
                on_already_initialized(name, existing_id)
        case _:
            if on_end:
                on_end(name, success=True, error_labels=())
    return outcome


def batch_init(
    albums: list[Path],
    *,
    dry_run: bool = False,
    new_id: Callable[[], str] = generate_album_id,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: OnStart = None,
    on_end: OnEnd = None,
    on_already_initialized: OnAlreadyInitialized = None,
) -> BatchInitResult:
    """
    Initialize album metadata for multiple albums.

    An album that already has an ID is left alone and counted as skipped:
    re-running init over a directory must not fail on the albums a previous
    run initialized. Calls ``on_start(name)`` before each album, then
    ``on_already_initialized(name, external_id)`` for a skipped album and
    ``on_end(name, success, error_labels)`` for any other.
    """
    outcomes = [
        _init_album(
            album_dir,
            name=display_fn(album_dir),
            dry_run=dry_run,
            new_id=new_id,
            on_start=on_start,
            on_end=on_end,
            on_already_initialized=on_already_initialized,
        )
        for album_dir in albums
    ]
    failures = failures_of(outcomes)
    skipped = sum(1 for o in outcomes if o.value is not None)
    return BatchInitResult(
        initialized=len(albums) - len(failures) - skipped,
        skipped=skipped,
        failures=failures,
    )
