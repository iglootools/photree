"""Shared helpers for fix operations."""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console

from ...common.formatting import CHECK
from ...fs import (
    MediaSource,
    display_path,
)

_console = Console(highlight=False)


def _delete_dir(directory: Path, *, dry_run: bool, log_cwd: Path | None) -> None:
    """Delete a directory and all its contents."""
    if not directory.is_dir():
        return

    if not dry_run:
        shutil.rmtree(directory)

    if log_cwd is not None:
        _console.print(
            f"{CHECK} {'[dry-run] ' if dry_run else ''}delete {display_path(directory, log_cwd)}"
        )


def _require_archive(album_dir: Path, ms: MediaSource) -> None:
    """Raise an error if the archive directory does not exist on disk.

    Prevents data loss on legacy std sources where browsable dirs ARE
    the originals (no ``std-{name}/`` archive yet).
    """
    if ms.is_std and not (album_dir / ms.archive_dir).is_dir():
        raise FileNotFoundError(
            f"Archive directory {ms.archive_dir} does not exist in {album_dir}. "
            f"Cannot run archive-dependent operations on legacy std media sources. "
            f"Migrate the album first."
        )
