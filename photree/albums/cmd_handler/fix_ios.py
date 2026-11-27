"""Batch fixing of iOS-specific album issues."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from photree.album.fix.ios import FixIosResult, run_fix_ios
from photree.albums.cmd_handler import (
    BatchFailure,
    OnEnd,
    OnStart,
    failures_of,
    run_album_step,
)


@dataclass(frozen=True)
class BatchFixIosResult:
    """
    Result of batch iOS fixing: how many albums were fixed, failures, results.

    *album_results* pairs each fixed album's display name with what its fix did.
    """

    fixed: int
    failures: tuple[BatchFailure, ...] = ()
    album_results: tuple[tuple[str, FixIosResult], ...] = ()


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
    """
    Fix iOS-specific issues on multiple albums.

    Calls ``on_start(name)`` before and ``on_end(name, success, error_labels)`` after
    each album.
    """

    def fix_one(album_dir: Path) -> FixIosResult:
        return run_fix_ios(
            album_dir,
            dry_run=dry_run,
            rm_orphan_sidecar=rm_orphan_sidecar,
            prefer_higher_quality_when_dups=prefer_higher_quality_when_dups,
            rm_miscategorized=rm_miscategorized,
            rm_miscategorized_safe=rm_miscategorized_safe,
            mv_miscategorized=mv_miscategorized,
        )

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
        album_results=tuple((o.name, o.value) for o in outcomes if o.value is not None),
    )
