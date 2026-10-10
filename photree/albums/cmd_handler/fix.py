"""Batch fix command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from ...album import fix as album_fixes
from ...album.fix.output import format_fix_result
from ...album.id import generate_album_id
from ...album.store.metadata import load_album_metadata, save_album_metadata
from ...album.store.protocol import AlbumMetadata
from . import BatchFailure, OnEnd, OnStart, failures_of, run_album_step


@dataclass(frozen=True)
class BatchFixResult:
    """Result of batch album fixing."""

    fixed: int
    failures: tuple[BatchFailure, ...] = ()
    # (album display name, report) for each album whose fix had something to say
    album_reports: tuple[tuple[str, str], ...] = ()

    @property
    def failed_albums(self) -> tuple[Path, ...]:
        return tuple(f.album_dir for f in self.failures)


@dataclass(frozen=True)
class _FixOptions:
    fix_id: bool
    new_id: bool
    rm_upstream: bool
    rm_orphan: bool
    dry_run: bool
    force: bool
    generate_id: Callable[[], str]


def _fix_one(album_dir: Path, opts: _FixOptions) -> str:
    """Fix one album; returns its report ("" when there is nothing to say)."""
    needs_id = (opts.fix_id and load_album_metadata(album_dir) is None) or opts.new_id
    if needs_id and not opts.dry_run:
        save_album_metadata(album_dir, AlbumMetadata(id=opts.generate_id()))

    if not (opts.rm_upstream or opts.rm_orphan):
        return ""
    result = album_fixes.run_fix(
        album_dir,
        dry_run=opts.dry_run,
        rm_upstream_flag=opts.rm_upstream,
        rm_orphan_flag=opts.rm_orphan,
        force=opts.force,
    )
    return "\n".join(format_fix_result(result))


def batch_fix(
    albums: list[Path],
    *,
    fix_id: bool = False,
    new_id: bool = False,
    rm_upstream: bool = False,
    rm_orphan: bool = False,
    dry_run: bool = False,
    force: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: OnStart = None,
    on_end: OnEnd = None,
    generate_id: Callable[[], str] = generate_album_id,
) -> BatchFixResult:
    """Fix multiple albums and return aggregated results.

    Calls ``on_start(name)`` before and ``on_end(name, success, error_labels)`` after
    each album. *force* is passed to rm-upstream (see :func:`album.fix.run_fix`).
    """
    opts = _FixOptions(
        fix_id,
        new_id,
        rm_upstream,
        rm_orphan,
        dry_run,
        force,
        generate_id,
    )
    outcomes = [
        run_album_step(
            album_dir,
            partial(_fix_one, album_dir, opts),
            name=display_fn(album_dir),
            on_start=on_start,
            on_end=on_end,
        )
        for album_dir in albums
    ]
    failures = failures_of(outcomes)
    return BatchFixResult(
        fixed=len(albums) - len(failures),
        failures=failures,
        album_reports=tuple((o.name, o.value) for o in outcomes if o.value),
    )
