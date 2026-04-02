"""Batch optimize command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...album import (
    check as album_preflight,
    optimize as album_optimize,
)
from ...fsprotocol import LinkMode


@dataclass(frozen=True)
class BatchOptimizeResult:
    """Result of batch album optimization."""

    optimized: int
    failed_albums: list[Path] = field(default_factory=list)


def batch_optimize(
    albums: list[Path],
    *,
    link_mode: LinkMode,
    check: bool = True,
    checksum: bool = True,
    sips_available: bool = True,
    dry_run: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool], None] | None = None,
) -> BatchOptimizeResult:
    """Optimize multiple albums and return aggregated results.

    Calls ``on_start(name)`` before and ``on_end(name, success)`` after
    each album.
    """
    optimized = 0
    failed_albums: list[Path] = []

    for album_dir in albums:
        album_name = display_fn(album_dir)
        if on_start:
            on_start(album_name)

        if check:
            check_result = album_preflight.run_album_check(
                album_dir,
                sips_available=sips_available,
                exiftool=None,
                checksum=checksum,
                check_naming_flag=False,
            )
            if not check_result.success:
                if on_end:
                    on_end(album_name, False)
                failed_albums.append(album_dir)
                continue

        album_optimize.optimize_album(album_dir, link_mode=link_mode, dry_run=dry_run)
        if on_end:
            on_end(album_name, True)
        optimized += 1

    return BatchOptimizeResult(optimized=optimized, failed_albums=failed_albums)
