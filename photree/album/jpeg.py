"""Image-to-JPEG conversion logic.

- HEIC and DNG (ProRAW) files are converted to JPEG using macOS ``sips``
  (preserves EXIF metadata).
- JPEG files are copied as-is. The main-img directory may contain JPEGs because
  some iPhones shoot in JPEG (e.g. when HEIF is disabled in Camera settings, or for
  certain camera modes), and Image Capture preserves the original format.
- Other files (videos, etc.) are skipped.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Protocol

from ..common.fs import file_ext, list_files
from ..common.parallelism import ParallelResult, run_parallel
from ..common.sips import convert_to_jpeg
from .formats import CONVERT_TO_JPEG_EXTENSIONS, COPY_AS_IS_TO_JPEG_EXTENSIONS

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class JpegAction(StrEnum):
    """What producing the JPEG variant of a browsable image involves."""

    CONVERT = "convert"  # HEIC/HEIF/DNG → JPEG via sips
    COPY = "copy"  # JPEG/PNG copied as-is
    SKIP = "skip"  # no JPEG variant (videos, unknown formats)


def jpeg_action(filename: str) -> JpegAction:
    """Classify *filename* by how its JPEG variant is produced."""
    match file_ext(filename):
        case ext if ext in CONVERT_TO_JPEG_EXTENSIONS:
            return JpegAction.CONVERT
        case ext if ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
            return JpegAction.COPY
        case _:
            return JpegAction.SKIP


def jpeg_name(filename: str) -> str | None:
    """Return the name of *filename*'s JPEG variant, or ``None`` if it has none."""
    match jpeg_action(filename):
        case JpegAction.CONVERT:
            return Path(filename).with_suffix(".jpg").name
        case JpegAction.COPY:
            return filename
        case JpegAction.SKIP:
            return None


# ---------------------------------------------------------------------------
# Single-file converters
# ---------------------------------------------------------------------------


class ConvertFile(Protocol):
    """Produce the JPEG variant of *src* in *dst_dir*.

    Returns the destination path, or ``None`` when the file was skipped.
    Implementations must be safe to call from worker threads.
    """

    def __call__(
        self, src: Path, dst_dir: Path, /, *, dry_run: bool
    ) -> Path | None: ...


def _produce_jpeg(
    src: Path,
    dst_dir: Path,
    *,
    dry_run: bool,
    convert: Callable[[Path, Path], object],
) -> Path | None:
    """Shared body of the converters: classify, then convert or copy."""
    target = jpeg_name(src.name)
    if target is None:
        return None
    dst = dst_dir / target
    if not dry_run:
        match jpeg_action(src.name):
            case JpegAction.CONVERT:
                convert(src, dst)
            case _:
                shutil.copy(src, dst)
    return dst


def convert_single_file(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    """Convert or copy a single file to the JPEG output directory.

    - HEIC/HEIF/DNG → converted to JPEG via ``sips`` (preserves EXIF metadata)
    - JPEG/JPG/PNG → copied as-is
    - Other → skipped (returns None)
    """
    return _produce_jpeg(src, dst_dir, dry_run=dry_run, convert=convert_to_jpeg)


def noop_convert_single(_src: Path, _dst_dir: Path, *, dry_run: bool) -> Path | None:
    """No-op converter that skips HEIC-to-JPEG conversion entirely."""
    return None


def copy_convert_single(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    """Copy-only converter: copies all files as-is without sips conversion.

    Use in integration tests on platforms where sips is unavailable. HEIC/DNG files are copied
    rather than converted, so the output is not true JPEG.
    """
    return _produce_jpeg(src, dst_dir, dry_run=dry_run, convert=shutil.copy)


# ---------------------------------------------------------------------------
# Directory refresh
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JpegConversionFailure:
    """A single file that could not be converted or copied."""

    filename: str
    reason: str


@dataclass(frozen=True)
class RefreshResult:
    """Result of a batch JPEG refresh.

    *converted* and *copied* count files that actually landed in the
    destination; a file that raised is counted in *failed* instead.
    """

    converted: int
    copied: int
    skipped: int
    failed: tuple[JpegConversionFailure, ...] = ()

    @property
    def success(self) -> bool:
        return not self.failed


def _clear_dir(directory: Path) -> None:
    """Delete the regular files of *directory*, creating it if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    for f in directory.iterdir():
        if f.is_file():
            f.unlink()


def refresh_jpeg_dir(
    src_dir: Path,
    dst_dir: Path,
    *,
    dry_run: bool = False,
    on_file_start: Callable[[str], None] | None = None,
    on_file_end: Callable[[str, bool], None] | None = None,
    convert_file: ConvertFile = convert_single_file,
    max_workers: int | None = None,
) -> RefreshResult:
    """Delete contents of *dst_dir* and re-convert all files from *src_dir*.

    The destination is cleared even when the source is empty or missing, so
    JPEGs of deleted images do not survive the refresh.

    Calls ``on_file_start(filename)`` before and ``on_file_end(filename, success)``
    after each convertible file; files with no JPEG variant are counted as
    skipped without callbacks.

    Conversions run in parallel when *max_workers* > 1, sequentially otherwise
    (the default). Both paths call *convert_file* and record a per-file
    failure instead of abandoning the directory.
    """
    if not dry_run and (src_dir.is_dir() or dst_dir.is_dir()):
        _clear_dir(dst_dir)

    all_files = list_files(src_dir)
    src_files = [f for f in all_files if jpeg_action(f) != JpegAction.SKIP]
    tasks = [
        (filename, partial(convert_file, src_dir / filename, dst_dir, dry_run=dry_run))
        for filename in src_files
    ]
    results = (
        run_parallel(
            tasks, max_workers=max_workers, on_start=on_file_start, on_end=on_file_end
        )
        if max_workers is not None and max_workers > 1
        else _run_sequential(tasks, on_start=on_file_start, on_end=on_file_end)
    )
    return _summarize(results, skipped=len(all_files) - len(src_files))


def _run_sequential(
    tasks: Sequence[tuple[str, Callable[[], Path | None]]],
    *,
    on_start: Callable[[str], None] | None,
    on_end: Callable[[str, bool], None] | None,
) -> list[ParallelResult[Path | None]]:
    """Run *tasks* one by one, with the same per-file contract as run_parallel."""
    # Documented exception (docs/guidelines.md): a per-item try/except in a
    # batch loop cannot be a comprehension.
    results: list[ParallelResult[Path | None]] = []
    for key, fn in tasks:
        if on_start:
            on_start(key)
        result: ParallelResult[Path | None]
        try:
            # SipsError is an OSError, as are copy failures; anything else is a
            # bug and propagates.
            result = ParallelResult(key=key, success=True, value=fn())
        except OSError as exc:
            result = ParallelResult(key=key, success=False, exception=exc)
        if on_end:
            on_end(key, result.success)
        results.append(result)
    return results


def _summarize(
    results: Sequence[ParallelResult[Path | None]], *, skipped: int
) -> RefreshResult:
    """Count outcomes from the results, not from the plan.

    Tallying before the work runs reports every file as converted even when
    sips failed on half of them. A converter returning ``None`` (e.g.
    :func:`noop_convert_single`) skipped the file deliberately.
    """
    landed = [r for r in results if r.success and r.value is not None]
    return RefreshResult(
        converted=sum(1 for r in landed if jpeg_action(r.key) == JpegAction.CONVERT),
        copied=sum(1 for r in landed if jpeg_action(r.key) == JpegAction.COPY),
        skipped=skipped + sum(1 for r in results if r.success and r.value is None),
        failed=tuple(
            JpegConversionFailure(filename=r.key, reason=r.error or "unknown error")
            for r in results
            if not r.success
        ),
    )
