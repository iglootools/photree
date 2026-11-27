"""Batch album fixing."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from photree.album import fix as album_fixes
from photree.album.fix import FixResult
from photree.album.id import generate_album_id
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.albums.cmd_handler import (
    BatchFailure,
    OnEnd,
    OnStart,
    failures_of,
    run_album_step,
)


@dataclass(frozen=True)
class BatchFixResult:
    """
    Result of batch album fixing: how many albums were fixed, failures, results.

    *album_results* pairs each album's display name with what its file fixes
    (``--rm-upstream``, ``--rm-orphan``) did, for every album that ran them.
    """

    fixed: int
    failures: tuple[BatchFailure, ...] = ()
    album_results: tuple[tuple[str, FixResult], ...] = ()


@dataclass(frozen=True)
class _FixOptions:
    fix_id: bool
    new_id: bool
    rm_upstream: bool
    rm_orphan: bool
    dry_run: bool
    force: bool
    generate_id: Callable[[], str]


def _fix_one(album_dir: Path, opts: _FixOptions) -> FixResult | None:
    """Fix one album; return what its file fixes did, ``None`` when none ran."""
    needs_id = (opts.fix_id and load_album_metadata(album_dir) is None) or opts.new_id
    if needs_id and not opts.dry_run:
        save_album_metadata(album_dir, AlbumMetadata(id=opts.generate_id()))

    return (
        album_fixes.run_fix(
            album_dir,
            dry_run=opts.dry_run,
            rm_upstream_flag=opts.rm_upstream,
            rm_orphan_flag=opts.rm_orphan,
            force=opts.force,
        )
        if opts.rm_upstream or opts.rm_orphan
        else None
    )


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
    """
    Fix multiple albums and return aggregated results.

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
        album_results=tuple((o.name, o.value) for o in outcomes if o.value is not None),
    )
