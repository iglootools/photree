"""Generic parallel task execution via :class:`~concurrent.futures.ThreadPoolExecutor`."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ParallelResult[T]:
    """Outcome of a single task within a parallel batch."""

    key: str
    success: bool
    value: T | None = None
    error: str | None = None


def run_parallel[T](
    tasks: Sequence[tuple[str, Callable[[], T]]],
    *,
    max_workers: int | None = None,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool], None] | None = None,
) -> list[ParallelResult[T]]:
    """Run *tasks* in parallel via :class:`ThreadPoolExecutor`.

    Each task is a ``(key, callable)`` pair. The callable's return value
    is captured in :attr:`ParallelResult.value` on success.

    *max_workers* defaults to :func:`os.cpu_count`. Callbacks
    *on_start*/*on_end* are called from worker threads — callers must
    ensure thread-safety (Rich progress bars are thread-safe).
    """
    if not tasks:
        return []

    workers = max_workers or os.cpu_count() or 4
    results: list[ParallelResult[T]] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_key = {
            pool.submit(_run_task, key, fn, on_start, on_end): key for key, fn in tasks
        }
        for future in as_completed(future_to_key):
            results.append(future.result())

    return results


def _run_task[T](
    key: str,
    fn: Callable[[], T],
    on_start: Callable[[str], None] | None,
    on_end: Callable[[str, bool], None] | None,
) -> ParallelResult[T]:
    """Execute a single task, calling optional callbacks."""
    if on_start:
        on_start(key)
    try:
        value = fn()
        if on_end:
            on_end(key, True)
        return ParallelResult(key=key, success=True, value=value)
    except Exception as exc:
        if on_end:
            on_end(key, False)
        return ParallelResult(key=key, success=False, error=str(exc))
