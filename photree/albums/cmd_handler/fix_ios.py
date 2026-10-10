"""Batch fix-ios command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ...album.fix.ios import run_fix_ios
from ...album.fix.ios.output import format_fix_ios_result
from . import BatchFailure, OnEnd, OnStart, failures_of, run_album_step


@dataclass(frozen=True)
class BatchFixIosResult:
    """Result of batch iOS album fixing."""

    fixed: int
    failures: tuple[BatchFailure, ...] = ()
    # (album display name, report) for each album whose fix had something to say
    album_reports: tuple[tuple[str, str], ...] = ()

    @property
    def failed_albums(self) -> tuple[Path, ...]:
        return tuple(f.album_dir for f in self.failures)


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
    on_start: OnStart = None,
    on_end: OnEnd = None,
) -> BatchFixIosResult:
    """Fix iOS-specific issues on multiple albums.

    Calls ``on_start(name)`` before and ``on_end(name, success, error_labels)`` after
    each album.
    """

    def fix_one(album_dir: Path) -> str:
        result = run_fix_ios(
            album_dir,
            dry_run=dry_run,
            rm_orphan_sidecar=rm_orphan_sidecar,
            prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
            rm_miscategorized=rm_miscategorized,
            rm_miscategorized_safe=rm_miscategorized_safe,
            mv_miscategorized=mv_miscategorized,
        )
        return "\n".join(format_fix_ios_result(result))

    outcomes = [
        run_album_step(
            album_dir,
            partial(fix_one, album_dir),
            name=display_fn(album_dir),
            on_start=on_start,
            on_end=on_end,
        )
        for album_dir in albums
    ]
    failures = failures_of(outcomes)
    return BatchFixIosResult(
        fixed=len(albums) - len(failures),
        failures=failures,
        album_reports=tuple((o.name, o.value) for o in outcomes if o.value),
    )
