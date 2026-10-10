"""Batch post-import check command handler."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from exiftool import ExifToolHelper  # type: ignore[import-untyped]

from ...album import check as album_check
from ...common.exif import exiftool_session
from ...foundation.linking import LinkMode


def run_batch_post_import_check(
    targets: list[Path],
    *,
    link_mode: LinkMode,
    sips_available: bool,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None = None,
) -> list[Path]:
    """Run post-import checks on imported albums.

    *sips_available* is probed and *link_mode* resolved by the caller (the CLI
    layer owns PATH and gallery lookups). Returns the list of albums that failed checking.
    """
    with exiftool_session() as exiftool:
        passed = [
            _check_one(
                target_dir,
                display_fn(target_dir),
                link_mode=link_mode,
                sips_available=sips_available,
                exiftool=exiftool,
                on_start=on_start,
                on_end=on_end,
            )
            for target_dir in targets
        ]
    return [t for t, ok in zip(targets, passed, strict=True) if not ok]


def _check_one(
    target_dir: Path,
    target_name: str,
    *,
    link_mode: LinkMode,
    sips_available: bool,
    exiftool: ExifToolHelper | None,
    on_start: Callable[[str], None] | None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None,
) -> bool:
    """Check one imported album, notifying start and end. Returns success."""
    if on_start:
        on_start(target_name)
    check_result = album_check.run_album_check(
        target_dir,
        sips_available=sips_available,
        exiftool=exiftool,
        link_mode=link_mode,
    )
    if on_end:
        on_end(target_name, check_result.success, check_result.error_labels)
    return check_result.success
