"""Batch stats command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ...album import stats as album_stats
from . import BatchFailure, OnEnd, OnStart, failures_of, run_album_step


@dataclass(frozen=True)
class BatchStatsResult:
    """Aggregated stats over the albums that could be read, plus failures."""

    stats: album_stats.AlbumsStats
    failures: tuple[BatchFailure, ...] = ()


def batch_stats(
    albums: list[Path],
    *,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: OnStart = None,
    on_end: OnEnd = None,
) -> BatchStatsResult:
    """Compute aggregated stats for multiple albums.

    Calls ``on_start(name)`` before and ``on_end(name, success, error_labels)``
    after each album. An album whose stats cannot be computed is recorded as
    a failure and left out of the aggregate instead of aborting the batch.
    """
    outcomes = [
        run_album_step(
            album_dir,
            partial(album_stats.compute_album_stats, album_dir),
            name=display_fn(album_dir),
            on_start=on_start,
            on_end=on_end,
        )
        for album_dir in albums
    ]
    return BatchStatsResult(
        stats=album_stats.albums_stats_from_album_stats(
            [o.value for o in outcomes if o.value is not None]
        ),
        failures=failures_of(outcomes),
    )
