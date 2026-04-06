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

from types import TracebackType
from typing import TypeVar

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
)

from ..common.formatting import CHECK, CROSS, WARNING, rich_warning_text


def _result_icon(success: bool) -> str:
    return CHECK if success else CROSS


class _ProgressContextMixin:
    """Mixin adding context manager support to progress bars."""

    def stop(self) -> None:  # noqa: B027 — overridden by subclasses
        ...

    def __enter__(self: _T) -> _T:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stop()


_T = TypeVar("_T")


class SilentProgressBar(_ProgressContextMixin):
    """Silent progress bar that shows a spinner and count but no per-file output.

    Usage::

        with SilentProgressBar(total=file_count, description="Checking") as bar:
            run_check(..., on_file_checked=bar.advance)
    """

    def __init__(self, total: int, description: str) -> None:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            transient=True,
        )
        self._progress.start()
        self._task_id = self._progress.add_task(f"{description}...", total=total)

    def advance(self, _filename: str, _success: bool) -> None:
        self._progress.advance(self._task_id)

    def stop(self) -> None:
        self._progress.stop()


class FileProgressBar(_ProgressContextMixin):
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
        self._total = total
        self._description = description
        self._done_description = done_description
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None

    def _ensure_started(self, label: str) -> None:
        if self._progress is None:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                transient=True,
            )
            self._progress.start()
            self._task_id = self._progress.add_task(
                f"{self._description} {label}...", total=self._total
            )
        else:
            assert self._task_id is not None
            self._progress.update(
                self._task_id, description=f"{self._description} {label}..."
            )

    def on_start(self, filename: str) -> None:
        self._ensure_started(filename)

    def on_end(self, filename: str, success: bool) -> None:
        self._ensure_started(filename)
        assert self._progress is not None
        assert self._task_id is not None
        self._progress.console.print(
            f"{_result_icon(success)} {self._done_description} {filename}"
        )
        self._progress.advance(self._task_id)

    def stop(self) -> None:
        if self._progress is not None:
            self._progress.stop()


class StageProgressBar(_ProgressContextMixin):
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
        self._total = total
        self._labels = labels or {}
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None

    def on_start(self, stage: str) -> None:
        label = self._labels.get(stage, stage)
        if self._progress is None:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                transient=True,
            )
            self._progress.start()
            self._task_id = self._progress.add_task(f"{label}...", total=self._total)
        else:
            assert self._task_id is not None
            self._progress.update(self._task_id, description=f"{label}...")

    def on_end(self, stage: str) -> None:
        if self._progress is not None:
            assert self._task_id is not None
            self._progress.console.print(f"{CHECK} {stage}")
            self._progress.advance(self._task_id)

    def stop(self) -> None:
        if self._progress is not None:
            self._progress.stop()


class BatchProgressBar(_ProgressContextMixin):
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
        self._total = total
        self._description = description
        self._done_description = done_description
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None

    def _ensure_started(self, description: str) -> None:
        if self._progress is None:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                transient=True,
            )
            self._progress.start()
            self._task_id = self._progress.add_task(description, total=self._total)
        else:
            assert self._task_id is not None
            self._progress.update(self._task_id, description=description)

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
        if self._progress is not None:
            assert self._task_id is not None
            has_warnings = bool(warning_labels)
            icon = WARNING if success and has_warnings else _result_icon(success)
            parts: list[str] = []
            if error_labels:
                parts.append(f"[red]| {', '.join(error_labels)}[/red]")
            if warning_labels:
                parts.append(rich_warning_text("| " + ", ".join(warning_labels)))
            suffix = f" {' '.join(parts)}" if parts else ""
            self._progress.console.print(
                f"{icon} {self._done_description} {album_name}{suffix}"
            )
            self._progress.advance(self._task_id)

    def on_skipped(self, album_name: str, reason: str) -> None:
        self._ensure_started(f"Skipping {album_name}...")
        if self._progress is not None:
            assert self._task_id is not None
            self._progress.console.print(f"{CROSS} {album_name} ({reason})")
            self._progress.advance(self._task_id)

    def stop(self) -> None:
        if self._progress is not None:
            self._progress.stop()
