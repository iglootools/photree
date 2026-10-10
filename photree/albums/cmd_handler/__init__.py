"""Command handlers for batch album operations.

Each module contains a single handler function + its result dataclass.
These functions orchestrate domain operations, accept ``on_*`` callbacks
for progress notification, and return structured results.

No module in this package imports ``typer``, ``rich``, or ``clihelpers``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BatchFailure:
    """One album that failed, and why.

    The reason is the point: a batch that reports only *which* albums failed
    forces the user to re-run each one individually to learn anything, which
    is the slowest possible way to deliver information the batch already had.
    """

    album_dir: Path
    reason: str


class AlbumStepError(Exception):
    """An album step that failed without crashing: reported, batch continues.

    ``labels`` are the short per-item labels shown on the progress line;
    ``reason`` is the one-line summary kept in the :class:`BatchFailure`.
    """

    def __init__(self, reason: str, labels: tuple[str, ...] = ()) -> None:
        self.reason = reason
        self.labels = labels or (reason,)
        super().__init__(reason)


@dataclass(frozen=True)
class StepOutcome[T]:
    """Result of one album step: a value on success, a failure otherwise."""

    album_dir: Path
    name: str
    value: T | None
    failure: BatchFailure | None


type OnStart = Callable[[str], None] | None
type OnEnd = Callable[[str, bool, tuple[str, ...]], None] | None


def run_album_step[T](
    album_dir: Path,
    step: Callable[[], T],
    *,
    name: str,
    on_start: OnStart = None,
    on_end: OnEnd = None,
) -> StepOutcome[T]:
    """Run *step* for one album, reporting progress and capturing any failure.

    Every exception becomes a :class:`BatchFailure` carrying its message:
    one bad album must never abort the batch nor be counted as a success.
    """
    if on_start:
        on_start(name)
    try:
        value = step()
    except AlbumStepError as exc:
        failure, labels = BatchFailure(album_dir, exc.reason), exc.labels
    except Exception as exc:
        failure, labels = BatchFailure(album_dir, str(exc)), (str(exc),)
    else:
        if on_end:
            on_end(name, True, ())
        return StepOutcome(album_dir, name, value, None)
    if on_end:
        on_end(name, False, labels)
    return StepOutcome(album_dir, name, None, failure)


def failures_of[T](outcomes: Iterable[StepOutcome[T]]) -> tuple[BatchFailure, ...]:
    """The failures among *outcomes*, in order."""
    return tuple(o.failure for o in outcomes if o.failure is not None)
