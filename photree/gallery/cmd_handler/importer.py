"""Gallery import command handlers (single and batch)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ...fsprotocol import LinkMode
from .. import importer as gallery_importer
from ..importer import AlbumImportResult


def run_single_import(
    album_dir: Path,
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
) -> AlbumImportResult:
    """Execute a single album import with optional stage callbacks.

    Raises :class:`ValueError` on import errors.
    """
    return gallery_importer.import_album(
        source_dir=album_dir,
        gallery_dir=gallery_dir,
        link_mode=link_mode,
        dry_run=dry_run,
        on_stage_start=on_stage_start,
        on_stage_end=on_stage_end,
    )


@dataclass(frozen=True)
class BatchImportResult:
    """Result of batch gallery import."""

    imported: int
    failed_albums: list[Path] = field(default_factory=list)


def run_batch_import(
    albums: list[Path],
    gallery_dir: Path,
    link_mode: LinkMode,
    dry_run: bool,
    *,
    on_start: Callable[[str], None] | None = None,
    on_end: Callable[[str, bool, tuple[str, ...]], None] | None = None,
) -> BatchImportResult:
    """Import multiple albums into a gallery.

    Calls ``on_start(name)`` before and
    ``on_end(name, success, error_labels)`` after each album.
    """
    imported = 0
    failed: list[Path] = []

    for album_path in albums:
        album_name = album_path.name
        if on_start:
            on_start(album_name)
        try:
            gallery_importer.import_album(
                source_dir=album_path,
                gallery_dir=gallery_dir,
                link_mode=link_mode,
                dry_run=dry_run,
            )
            if on_end:
                on_end(album_name, True, ())
            imported += 1
        except (ValueError, OSError) as exc:
            if on_end:
                on_end(album_name, False, (str(exc)[:60],))
            failed.append(album_path)

    return BatchImportResult(imported=imported, failed_albums=failed)
