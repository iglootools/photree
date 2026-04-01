"""Rich progress bars for import commands, following the nbkp pattern.

Each progress bar is transient (disappears after completion) and prints
result lines (✓/✗) above the bar as each unit completes.
"""

from __future__ import annotations

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
)

from ..uiconventions import CHECK, CROSS, WARNING, rich_warning_text


def _result_icon(success: bool) -> str:
    return CHECK if success else CROSS


class SilentProgressBar:
    """Silent progress bar that shows a spinner and count but no per-file output.

    Usage::

        bar = SilentProgressBar(total=file_count)
        run_check(..., on_file_checked=bar.advance)
        bar.stop()
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


class FileProgressBar:
    """Progress bar for per-file operations — one check line per file.

    Usage::

        bar = FileProgressBar(total=file_count)
        run_check(..., on_file_checked=bar.on_end)
        bar.stop()
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


class StageProgressBar:
    """Progress bar for stage-based operations — one check line per stage.

    Usage::

        bar = StageProgressBar(total=4, labels={"build": "Building"})
        run_import(
            ...,
            on_stage_start=bar.on_start,
            on_stage_end=bar.on_end,
        )
        bar.stop()
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


class BatchProgressBar:
    """Progress bar for batch import — one check line per album subdirectory.

    Usage::

        bar = BatchProgressBar(total=len(subdirs))
        # for each album:
        bar.on_start(album_name)
        bar.on_end(album_name, success=True)
        # or:
        bar.on_skipped(album_name, reason)
        bar.stop()
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
