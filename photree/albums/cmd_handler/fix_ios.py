"""Batch fix-ios command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...album.fix.ios import run_fix_ios
from ...album.fix.ios.output import format_fix_ios_result


@dataclass(frozen=True)
class BatchFixIosResult:
    """Result of batch iOS album fixing."""

    fixed: int
    failed_albums: list[Path] = field(default_factory=list)
    album_reports: list[tuple[str, str]] = field(default_factory=list)


def batch_fix_ios(
    albums: list[Path],
    *,
    dry_run: bool = False,
    rm_orphan_sidecar: bool = False,
    prefer_higher_quality_when_dups: bool = False,
    rm_miscategorized: bool = False,
    rm_miscategorized_safe: bool = False,
    mv_miscategorized: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool], None] | None = None,
) -> BatchFixIosResult:
    """Fix iOS-specific issues on multiple albums.

    Calls ``on_start(name)`` before and ``on_end(name, success)`` after
    each album.
    """
    fixed = 0
    failed_albums: list[Path] = []
    album_reports: list[tuple[str, str]] = []

    for album_dir in albums:
        album_name = display_fn(album_dir)
        if on_start:
            on_start(album_name)

        try:
            result = run_fix_ios(
                album_dir,
                dry_run=dry_run,
                rm_orphan_sidecar=rm_orphan_sidecar,
                prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
                rm_miscategorized=rm_miscategorized,
                rm_miscategorized_safe=rm_miscategorized_safe,
                mv_miscategorized=mv_miscategorized,
            )
            if on_end:
                on_end(album_name, True)
            fixed += 1
            lines = format_fix_ios_result(result)
            if lines:
                album_reports.append((album_name, "\n".join(lines)))
        except Exception:
            if on_end:
                on_end(album_name, False)
            failed_albums.append(album_dir)

    return BatchFixIosResult(
        fixed=fixed,
        failed_albums=failed_albums,
        album_reports=album_reports,
    )
