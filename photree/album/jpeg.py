"""Image-to-JPEG conversion logic.

- HEIC and DNG (ProRAW) files are converted to JPEG using macOS ``sips``
  (preserves EXIF metadata).
- JPEG files are copied as-is. The main-img directory may contain JPEGs because
  some iPhones shoot in JPEG (e.g. when HEIF is disabled in Camera settings, or for
  certain camera modes), and Image Capture preserves the original format.
- Other files (PNG, etc.) are skipped.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ..common.fs import file_ext, list_files
from ..common.sips import convert_to_jpeg, run_parallel
from .store.protocol import CONVERT_TO_JPEG_EXTENSIONS, COPY_AS_IS_TO_JPEG_EXTENSIONS


def convert_single_file(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    """Convert or copy a single file to the JPEG output directory.

    - HEIC → converted to JPEG via ``sips`` (preserves EXIF metadata)
    - JPEG/JPG/PNG → copied as-is
    - Other → skipped (returns None)
    """
    ext = file_ext(src.name)

    if ext in CONVERT_TO_JPEG_EXTENSIONS:
        dst = dst_dir / Path(src.name).with_suffix(".jpg").name
        if not dry_run:
            convert_to_jpeg(src, dst)
        return dst
    elif ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
        dst = dst_dir / src.name
        if not dry_run:
            shutil.copy(src, dst_dir)
        return dst
    else:
        return None


def noop_convert_single(_src: Path, _dst_dir: Path, *, dry_run: bool) -> Path | None:
    """No-op converter that skips HEIC-to-JPEG conversion entirely."""
    return None


def copy_convert_single(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    """Copy-only converter: copies all files as-is without sips conversion.

    Use in integration tests on platforms where sips is unavailable. HEIC/DNG files are copied
    rather than converted, so the output is not true JPEG.
    """
    ext = file_ext(src.name)

    if ext in CONVERT_TO_JPEG_EXTENSIONS:
        dst = dst_dir / Path(src.name).with_suffix(".jpg").name
        if not dry_run:
            shutil.copy(src, dst)
        return dst
    elif ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
        dst = dst_dir / src.name
        if not dry_run:
            shutil.copy(src, dst_dir)
        return dst
    else:
        return None


@dataclass(frozen=True)
class RefreshResult:
    """Result of a batch JPEG refresh."""

    converted: int
    copied: int
    skipped: int


def _classify_file(
    filename: str,
) -> str:
    """Classify a file as 'convert', 'copy', or 'skip'."""
    ext = file_ext(filename)
    if ext in CONVERT_TO_JPEG_EXTENSIONS:
        return "convert"
    elif ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
        return "copy"
    else:
        return "skip"


def refresh_jpeg_dir(
    src_dir: Path,
    dst_dir: Path,
    *,
    dry_run: bool = False,
    on_file_start: Callable[[str], None] | None = None,
    on_file_end: Callable[[str, bool], None] | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
    max_workers: int | None = None,
) -> RefreshResult:
    """Delete contents of *dst_dir* and re-convert all files from *src_dir*.

    Calls ``on_file_start(filename)`` before and ``on_file_end(filename, success)``
    after each file.

    When *max_workers* > 1, conversions run in parallel via
    :class:`~concurrent.futures.ThreadPoolExecutor`.  Defaults to sequential
    when *max_workers* is ``None``.
    """
    if not src_dir.is_dir():
        return RefreshResult(converted=0, copied=0, skipped=0)

    src_files = list_files(src_dir)
    if not src_files:
        return RefreshResult(converted=0, copied=0, skipped=0)

    # Clear destination
    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)
        for f in dst_dir.iterdir():
            if f.is_file():
                f.unlink()

    use_parallel = (
        max_workers is not None
        and max_workers > 1
        and convert_file is convert_single_file
    )

    if use_parallel:
        return _refresh_parallel(
            src_dir,
            dst_dir,
            src_files,
            dry_run=dry_run,
            on_file_start=on_file_start,
            on_file_end=on_file_end,
            max_workers=max_workers,
        )
    else:
        return _refresh_sequential(
            src_dir,
            dst_dir,
            src_files,
            dry_run=dry_run,
            on_file_start=on_file_start,
            on_file_end=on_file_end,
            convert_file=convert_file,
        )


def _refresh_sequential(
    src_dir: Path,
    dst_dir: Path,
    src_files: list[str],
    *,
    dry_run: bool,
    on_file_start: Callable[[str], None] | None,
    on_file_end: Callable[[str, bool], None] | None,
    convert_file: Callable[..., Path | None],
) -> RefreshResult:
    """Process files sequentially (original behavior)."""
    converted = 0
    copied = 0
    skipped = 0

    for filename in src_files:
        src = src_dir / filename
        if not src.is_file():
            skipped += 1
            continue

        if on_file_start:
            on_file_start(filename)

        result = convert_file(src, dst_dir, dry_run=dry_run)

        if result is None:
            skipped += 1
            if on_file_end:
                on_file_end(filename, False)
        elif file_ext(filename) in CONVERT_TO_JPEG_EXTENSIONS:
            converted += 1
            if on_file_end:
                on_file_end(filename, True)
        else:
            copied += 1
            if on_file_end:
                on_file_end(filename, True)

    return RefreshResult(converted=converted, copied=copied, skipped=skipped)


def _refresh_parallel(
    src_dir: Path,
    dst_dir: Path,
    src_files: list[str],
    *,
    dry_run: bool,
    on_file_start: Callable[[str], None] | None,
    on_file_end: Callable[[str, bool], None] | None,
    max_workers: int | None,
) -> RefreshResult:
    """Process files in parallel using :func:`run_parallel`."""
    tasks: list[tuple[str, Callable[[], object]]] = []
    converted = 0
    copied = 0
    skipped = 0

    for filename in src_files:
        src = src_dir / filename
        if not src.is_file():
            skipped += 1
            continue

        category = _classify_file(filename)
        match category:
            case "convert":
                dst = dst_dir / Path(filename).with_suffix(".jpg").name
                tasks.append(
                    (
                        filename,
                        partial(convert_to_jpeg, src, dst) if not dry_run else _noop,
                    )
                )
                converted += 1
            case "copy":
                dst = dst_dir / filename
                tasks.append(
                    (
                        filename,
                        partial(shutil.copy, src, dst_dir) if not dry_run else _noop,
                    )
                )
                copied += 1
            case _:
                skipped += 1

    run_parallel(
        tasks,
        max_workers=max_workers,
        on_start=on_file_start,
        on_end=on_file_end,
    )

    return RefreshResult(converted=converted, copied=copied, skipped=skipped)


def _noop() -> None:
    """No-op for dry-run parallel tasks."""
