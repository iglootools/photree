"""Rich progress bars for import commands, following the nbkp pattern.

Each progress bar is transient (disappears after completion) and prints
result lines (✓/✗) above the bar as each unit completes.

All progress bars support context manager usage::

    with BatchProgressBar(total=10, ...) as bar:
        bar.on_start("album")
        bar.on_end("album", success=True)
    # .stop() called automatically
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Self

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
)

from ..common.formatting import CHECK, CROSS, WARN_SIGN, WARNING, rich_warning_text


def _result_icon(success: bool) -> str:
    return CHECK if success else CROSS


def _new_progress() -> Progress:
    """Build the transient spinner + bar + M/N progress shared by all bars."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        transient=True,
    )


class _LazyProgress:
    """Base for progress bars: lazily started Rich progress with one task.

    Starting on first use keeps a command that ends up doing nothing from
    flashing an empty bar. Every result-line method goes through
    :meth:`_ensure_started`, so a result reported without a preceding
    ``on_start`` is still printed rather than silently dropped.
    """

    def __init__(self, total: int) -> None:
        self._total = total
        self._started: tuple[Progress, TaskID] | None = None

    def _ensure_started(self, description: str) -> tuple[Progress, TaskID]:
        match self._started:
            case None:
                progress = _new_progress()
                progress.start()
                task_id = progress.add_task(description, total=self._total)
                self._started = (progress, task_id)
                return self._started
            case (progress, task_id):
                progress.update(task_id, description=description)
                return self._started

    def _print_result(self, description: str, line: str) -> None:
        """Print *line* above the bar and advance it (starting it if needed)."""
        progress, task_id = self._ensure_started(description)
        progress.console.print(line)
        progress.advance(task_id)

    def stop(self) -> None:
        if self._started is not None:
            self._started[0].stop()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()


class SilentProgressBar(_LazyProgress):
    """Silent progress bar that shows a spinner and count but no per-file output.

    Usage::

        with SilentProgressBar(total=file_count, description="Checking") as bar:
            run_check(..., on_file_checked=bar.advance)
    """

    def __init__(self, total: int, description: str) -> None:
        super().__init__(total)
        self._description = f"{description}..."
        self._ensure_started(self._description)

    def advance(self, _filename: str, _success: bool) -> None:
        progress, task_id = self._ensure_started(self._description)
        progress.advance(task_id)


class FileProgressBar(_LazyProgress):
    """Progress bar for per-file operations — one check line per file.

    Usage::

        with FileProgressBar(total=file_count, ...) as bar:
            run_check(..., on_file_checked=bar.on_end)
    """

    def __init__(
        self,
        total: int,
        description: str,
        done_description: str,
    ) -> None:
        super().__init__(total)
        self._description = description
        self._done_description = done_description

    def on_start(self, filename: str) -> None:
        self._ensure_started(f"{self._description} {filename}...")

    def on_end(self, filename: str, success: bool) -> None:
        self._print_result(
            f"{self._description} {filename}...",
            f"{_result_icon(success)} {self._done_description} {filename}",
        )


class StageProgressBar(_LazyProgress):
    """Progress bar for stage-based operations — one check line per stage.

    Usage::

        with StageProgressBar(total=4, labels={"build": "Building"}) as bar:
            run_import(
                ...,
                on_stage_start=bar.on_start,
                on_stage_end=bar.on_end,
            )
    """

    def __init__(self, total: int, labels: dict[str, str] | None = None) -> None:
        super().__init__(total)
        self._labels = labels or {}

    def _stage_description(self, stage: str) -> str:
        return f"{self._labels.get(stage, stage)}..."

    def on_start(self, stage: str) -> None:
        self._ensure_started(self._stage_description(stage))

    def on_end(self, stage: str) -> None:
        self._print_result(self._stage_description(stage), f"{CHECK} {stage}")


class BatchProgressBar(_LazyProgress):
    """Progress bar for batch operations — one check line per album/item.

    Usage::

        with BatchProgressBar(total=len(items), ...) as bar:
            for item in items:
                bar.on_start(item.name)
                bar.on_end(item.name, success=True)
    """

    def __init__(
        self,
        total: int,
        description: str,
        done_description: str,
    ) -> None:
        super().__init__(total)
        self._description = description
        self._done_description = done_description

    def on_start(self, album_name: str) -> None:
        self._ensure_started(f"{self._description} {album_name}...")

    def on_end(
        self,
        album_name: str,
        *,
        success: bool,
        error_labels: tuple[str, ...] = (),
        warning_labels: tuple[str, ...] = (),
    ) -> None:
        icon = WARNING if success and warning_labels else _result_icon(success)
        fragments = [
            *([f"[red]| {', '.join(error_labels)}[/red]"] if error_labels else []),
            *(
                [rich_warning_text("| " + ", ".join(warning_labels))]
                if warning_labels
                else []
            ),
        ]
        suffix = "".join(f" {fragment}" for fragment in fragments)
        self._print_result(
            f"{self._description} {album_name}...",
            f"{icon} {self._done_description} {album_name}{suffix}",
        )

    def on_skipped(self, album_name: str, reason: str, *, warn: bool = False) -> None:
        icon = WARN_SIGN if warn else CROSS
        self._print_result(
            f"Skipping {album_name}...", f"{icon} {album_name} ({reason})"
        )


# ---------------------------------------------------------------------------
# Transient spinner for slow one-off operations
# ---------------------------------------------------------------------------


def run_with_spinner[T](description: str, fn: Callable[[], T]) -> T:
    """Run *fn* with a transient spinner showing *description*."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description, total=None)
        return fn()
