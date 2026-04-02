"""Batch fix command handler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...album import fix as album_fixes
from ...album.fix.output import format_fix_result
from ...album.store.metadata import load_album_metadata, save_album_metadata
from ...album.id import generate_album_id
from ...album.store.protocol import AlbumMetadata
from ...fsprotocol import LinkMode


@dataclass(frozen=True)
class BatchFixResult:
    """Result of batch album fixing."""

    fixed: int
    failed_albums: list[Path] = field(default_factory=list)
    album_reports: list[tuple[str, str]] = field(default_factory=list)


def batch_fix(
    albums: list[Path],
    *,
    fix_id: bool = False,
    new_id: bool = False,
    link_mode: LinkMode = LinkMode.HARDLINK,
    refresh_browsable: bool = False,
    refresh_jpeg: bool = False,
    rm_upstream: bool = False,
    rm_orphan: bool = False,
    dry_run: bool = False,
    display_fn: Callable[[Path], str] = lambda p: p.name,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool], None] | None = None,
) -> BatchFixResult:
    """Fix multiple albums and return aggregated results.

    Calls ``on_start(name)`` before and ``on_end(name, success)`` after
    each album.
    """
    any_archive_op = refresh_browsable or refresh_jpeg or rm_upstream or rm_orphan

    fixed = 0
    failed_albums: list[Path] = []
    album_reports: list[tuple[str, str]] = []

    for album_dir in albums:
        album_name = display_fn(album_dir)
        if on_start:
            on_start(album_name)

        try:
            needs_id = (fix_id and load_album_metadata(album_dir) is None) or new_id
            if needs_id and not dry_run:
                save_album_metadata(album_dir, AlbumMetadata(id=generate_album_id()))

            if any_archive_op:
                result = album_fixes.run_fix(
                    album_dir,
                    link_mode=link_mode,
                    dry_run=dry_run,
                    refresh_browsable_flag=refresh_browsable,
                    refresh_jpeg_flag=refresh_jpeg,
                    rm_upstream_flag=rm_upstream,
                    rm_orphan_flag=rm_orphan,
                )
                lines = format_fix_result(result)
                if lines:
                    album_reports.append((album_name, "\n".join(lines)))

            if on_end:
                on_end(album_name, True)
            fixed += 1
        except Exception:
            if on_end:
                on_end(album_name, False)
            failed_albums.append(album_dir)

    return BatchFixResult(
        fixed=fixed,
        failed_albums=failed_albums,
        album_reports=album_reports,
    )
