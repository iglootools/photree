"""macOS ``sips`` wrapper — image conversion, resizing, and metadata queries.

All functions build argument lists rather than shell strings to avoid quoting
issues. The ``_parallel`` variants run multiple ``sips`` subprocesses
concurrently via :class:`~concurrent.futures.ThreadPoolExecutor`.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Single-file operations
# ---------------------------------------------------------------------------


def convert_to_jpeg(src: Path, dst: Path) -> None:
    """Convert *src* to JPEG via ``sips``, writing to *dst*.

    Preserves EXIF metadata. Works with HEIC, DNG, JPEG, PNG, etc.
    """
    subprocess.run(
        ["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)],
        check=True,
        capture_output=True,
    )


def resize_to_jpeg(src: Path, dst: Path, *, max_dimension: int) -> None:
    """Convert *src* to a resized JPEG (longest edge ≤ *max_dimension*).

    Uses ``--resampleHeightWidthMax`` so the aspect ratio is preserved.
    """
    subprocess.run(
        [
            "sips",
            "-s",
            "format",
            "jpeg",
            "--resampleHeightWidthMax",
            str(max_dimension),
            str(src),
            "--out",
            str(dst),
        ],
        check=True,
        capture_output=True,
    )


def get_dimensions(path: Path) -> tuple[int, int]:
    """Return ``(width, height)`` of an image file via ``sips``."""
    result = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    width = height = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            width = int(line.split(":")[1].strip())
        elif line.startswith("pixelHeight:"):
            height = int(line.split(":")[1].strip())
    return (width, height)


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelResult:
    """Outcome of a single task within a parallel batch."""

    key: str
    success: bool
    error: str | None = None


def run_parallel(
    tasks: Sequence[tuple[str, Callable[[], object]]],
    *,
    max_workers: int | None = None,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool], None] | None = None,
) -> list[ParallelResult]:
    """Run *tasks* in parallel via :class:`ThreadPoolExecutor`.

    Each task is a ``(key, callable)`` pair.  *max_workers* defaults to
    :func:`os.cpu_count`.  Callbacks *on_start*/*on_end* are called from
    worker threads — callers must ensure thread-safety (Rich progress bars
    are thread-safe).
    """
    if not tasks:
        return []

    workers = max_workers or os.cpu_count() or 4
    results: list[ParallelResult] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_key = {
            pool.submit(_run_task, key, fn, on_start, on_end): key for key, fn in tasks
        }
        for future in as_completed(future_to_key):
            results.append(future.result())

    return results


def _run_task(
    key: str,
    fn: Callable[[], object],
    on_start: Callable[[str], None] | None,
    on_end: Callable[[str, bool], None] | None,
) -> ParallelResult:
    """Execute a single task, calling optional callbacks."""
    if on_start:
        on_start(key)
    try:
        fn()
        if on_end:
            on_end(key, True)
        return ParallelResult(key=key, success=True)
    except Exception as exc:
        if on_end:
            on_end(key, False)
        return ParallelResult(key=key, success=False, error=str(exc))
