"""
Command handlers for batch album operations.

Each module contains a single handler function + its result dataclass.
These functions orchestrate domain operations, accept ``on_*`` callbacks
for progress notification, and return structured results.

No module in this package imports ``typer``, ``rich``, or ``clihelpers``.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from photree.common.progress import ItemEnd


@dataclass(frozen=True)
class BatchFailure:
    """
    One album that failed, and why.

    The reason is the point: a batch that reports only *which* albums failed
    forces the user to re-run each one individually to learn anything, which
    is the slowest possible way to deliver information the batch already had.
    *error* is the exception the album's step raised, for a caller that needs
    more than the reason's wording.
    """

    album_dir: Path
    reason: str
    error: Exception | None = None


class AlbumStepError(Exception):
    """
    An album step that failed without crashing: reported, batch continues.

    ``labels`` are the short per-item labels shown on the progress line;
    ``reason`` is the one-line summary kept in the :class:`BatchFailure`.
    """

    def __init__(self, reason: str, labels: tuple[str, ...] = ()) -> None:
        """Build the error from its *reason* and *labels*, which default to *reason*."""
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
type OnEnd = ItemEnd | None
type DescribeErrorFn = Callable[[Exception], tuple[str, tuple[str, ...]]]
"""Word a failed step's exception: its reason, then its progress labels."""


def describe_step_error(exc: Exception) -> tuple[str, tuple[str, ...]]:
    """
    Return the reason and progress labels of a failed step's exception.

    An :class:`AlbumStepError` carries its own; any other exception is shown
    as raised. A command whose steps raise a structured error passes its own
    :data:`DescribeErrorFn`, from its output layer, falling back on this one.
    """
    match exc:
        case AlbumStepError(reason=reason, labels=labels):
            return reason, labels
        case _:
            return str(exc), (str(exc),)


def run_album_step[T](
    album_dir: Path,
    step: Callable[[], T],
    *,
    name: str,
    on_start: OnStart = None,
    on_end: OnEnd = None,
    describe_error: DescribeErrorFn = describe_step_error,
) -> StepOutcome[T]:
    """
    Run *step* for one album, reporting progress and capturing any failure.

    Every exception becomes a :class:`BatchFailure` carrying the reason
    *describe_error* gives it: one bad album must never abort the batch nor
    be counted as a success.
    """
    if on_start:
        on_start(name)
    try:
        value = step()
    except Exception as exc:
        reason, labels = describe_error(exc)
        failure = BatchFailure(album_dir, reason, exc)
    else:
        if on_end:
            on_end(name, success=True, error_labels=())
        return StepOutcome(album_dir, name, value, None)
    if on_end:
        on_end(name, success=False, error_labels=labels)
    return StepOutcome(album_dir, name, None, failure)


def failures_of[T](outcomes: Iterable[StepOutcome[T]]) -> tuple[BatchFailure, ...]:
    """Return the failures among *outcomes*, in order."""
    return tuple(o.failure for o in outcomes if o.failure is not None)
