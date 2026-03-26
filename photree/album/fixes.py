"""Generic fix operations for all album contributor types.

Unlike :mod:`ios_fixes` which requires iOS contributors, these operations
work with both iOS and plain contributors.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import jpeg
from .jpeg import RefreshResult, convert_single_file
from ..fsprotocol import Contributor


def refresh_jpeg(
    album_dir: Path,
    contrib: Contributor,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
    on_file_start: Callable[[str], None] | None = None,
    on_file_end: Callable[[str, bool], None] | None = None,
) -> RefreshResult:
    """Refresh ``{contributor}-jpg/`` from ``{contributor}-img/``.

    Works for both iOS and plain contributors. Raises
    :class:`FileNotFoundError` if the source image directory does not exist.
    """
    src_dir = album_dir / contrib.img_dir
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Directory not found: {src_dir}")

    # When progress callbacks are provided, skip per-file verbose logging —
    # the progress bar already provides feedback.
    jpeg_log_cwd = log_cwd if on_file_end is None else None
    return jpeg.refresh_jpeg_dir(
        src_dir,
        album_dir / contrib.jpg_dir,
        dry_run=dry_run,
        log_cwd=jpeg_log_cwd,
        convert_file=convert_file,
        on_file_start=on_file_start,
        on_file_end=on_file_end,
    )
