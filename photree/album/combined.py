"""Rebuild main directories from orig/edited sources.

The main directories contain the "best" version of each media file:
- If an edited version exists (IMG_E* prefix), use it
- Otherwise, use the original

This is the same logic used during import (see importer.image_capture),
extracted here so it can be reused by fix commands.
"""

from __future__ import annotations

import errno
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from ..fsprotocol import LinkMode, dedup_media_dict, display_path, list_files
from ..uiconventions import CHECK

_console = Console(highlight=False)


def compute_main_files(
    orig_dir: Path,
    edit_dir: Path,
    media_extensions: frozenset[str],
) -> list[tuple[str, Path]]:
    """Compute which files should go into main: (filename, source_dir) pairs.

    For each media number in orig, picks the edited version if available,
    otherwise the original.
    """
    orig_files = list_files(orig_dir)
    edit_files = list_files(edit_dir)

    orig_by_number = dedup_media_dict(orig_files, media_extensions)
    edit_by_number = dedup_media_dict(edit_files, media_extensions)

    return sorted(
        [
            *(
                (edit_by_number[num], edit_dir)
                for num in orig_by_number
                if num in edit_by_number
            ),
            *(
                (orig_name, orig_dir)
                for num, orig_name in orig_by_number.items()
                if num not in edit_by_number
            ),
        ],
        key=lambda pair: pair[0],
    )


_LINK_MODE_VERBS: dict[LinkMode, str] = {
    LinkMode.COPY: "copy",
    LinkMode.HARDLINK: "hardlink",
    LinkMode.SYMLINK: "symlink",
}


def _place_file(src: Path, dst: Path, link_mode: LinkMode) -> None:
    """Place a file into the main directory using the specified link mode."""
    match link_mode:
        case LinkMode.COPY:
            shutil.copy(src, dst)
        case LinkMode.HARDLINK:
            try:
                os.link(src, dst)
            except OSError as exc:
                if exc.errno == errno.EXDEV:
                    raise OSError(
                        f"Cannot create hardlink across filesystems: {src} → {dst}. "
                        f"Use --link-mode symlink instead."
                    ) from exc
                raise
        case LinkMode.SYMLINK:
            rel_src = os.path.relpath(src, dst.parent)
            os.symlink(rel_src, dst)


@dataclass(frozen=True)
class RefreshMainDirResult:
    """Result of refreshing a single main directory."""

    copied: int


def refresh_main_dir(
    orig_dir: Path,
    edit_dir: Path,
    main_dir: Path,
    *,
    media_extensions: frozenset[str],
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    log_cwd: Path | None = None,
    on_file_start: Callable[[str], None] | None = None,
    on_file_end: Callable[[str, bool], None] | None = None,
) -> RefreshMainDirResult:
    """Rebuild a main directory from orig and edited sources.

    Clears the main directory and re-populates it with the best version
    of each file (edited if available, otherwise original).
    """
    if not orig_dir.is_dir():
        return RefreshMainDirResult(copied=0)

    files_to_copy = compute_main_files(orig_dir, edit_dir, media_extensions)

    if not files_to_copy:
        return RefreshMainDirResult(copied=0)

    # Clear and recreate destination
    if not dry_run:
        if main_dir.is_dir():
            for f in os.listdir(main_dir):
                (main_dir / f).unlink()
        main_dir.mkdir(parents=True, exist_ok=True)
        if log_cwd is not None:
            _console.print(f"{CHECK} clear {display_path(main_dir, log_cwd)}")
    elif log_cwd is not None:
        _console.print(f"{CHECK} [dry-run] clear {display_path(main_dir, log_cwd)}")

    verb = _LINK_MODE_VERBS[link_mode]

    for filename, source_dir in files_to_copy:
        if on_file_start:
            on_file_start(filename)

        if not dry_run:
            _place_file(source_dir / filename, main_dir / filename, link_mode)

        if log_cwd is not None:
            src = source_dir / filename
            dst = main_dir / filename
            _console.print(
                f"{CHECK} {'[dry-run] ' if dry_run else ''}{verb} {display_path(src, log_cwd)} → {display_path(dst, log_cwd)}"
            )

        if on_file_end:
            on_file_end(filename, True)

    return RefreshMainDirResult(copied=len(files_to_copy))
