"""Single album gallery import command handler."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ...fs import LinkMode
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
