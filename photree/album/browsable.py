"""Rebuild browsable directories from orig/edited archive sources.

The browsable directories contain the "best" version of each media file:
- If an edited version exists, use it
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

from ..fs import LinkMode, display_path, list_files
from ..fs.media import dedup_media_dict
from ..fs.protocol import _KeyFn
from ..common.formatting import CHECK

_console = Console(highlight=False)


def compute_browsable_files(
    orig_dir: Path,
    edit_dir: Path,
    media_extensions: frozenset[str],
    key_fn: _KeyFn,
) -> list[tuple[str, Path]]:
    """Compute which files should populate a browsable dir: (filename, source_dir) pairs.

    For each media key in orig, picks the edited version if available,
    otherwise the original.
    """
    orig_files = list_files(orig_dir)
    edit_files = list_files(edit_dir)

    orig_by_key = dedup_media_dict(orig_files, media_extensions, key_fn)
    edit_by_key = dedup_media_dict(edit_files, media_extensions, key_fn)

    return sorted(
        [
            *(
                (edit_by_key[key], edit_dir)
                for key in orig_by_key
                if key in edit_by_key
            ),
            *(
                (orig_name, orig_dir)
                for key, orig_name in orig_by_key.items()
                if key not in edit_by_key
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
    """Place a file into the browsable directory using the specified link mode."""
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
class RefreshBrowsableDirResult:
    """Result of refreshing a single browsable directory."""

    copied: int


def refresh_browsable_dir(
    orig_dir: Path,
    edit_dir: Path,
    browsable_dir: Path,
    *,
    media_extensions: frozenset[str],
    key_fn: _KeyFn,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    log_cwd: Path | None = None,
    on_file_start: Callable[[str], None] | None = None,
    on_file_end: Callable[[str, bool], None] | None = None,
) -> RefreshBrowsableDirResult:
    """Rebuild a browsable directory from orig and edited archive sources.

    Clears the browsable directory and re-populates it with the best version
    of each file (edited if available, otherwise original).
    """
    if not orig_dir.is_dir():
        return RefreshBrowsableDirResult(copied=0)

    files_to_copy = compute_browsable_files(
        orig_dir, edit_dir, media_extensions, key_fn
    )

    if not files_to_copy:
        return RefreshBrowsableDirResult(copied=0)

    # Clear and recreate destination
    if not dry_run:
        if browsable_dir.is_dir():
            for f in os.listdir(browsable_dir):
                (browsable_dir / f).unlink()
        browsable_dir.mkdir(parents=True, exist_ok=True)
        if log_cwd is not None:
            _console.print(f"{CHECK} clear {display_path(browsable_dir, log_cwd)}")
    elif log_cwd is not None:
        _console.print(
            f"{CHECK} [dry-run] clear {display_path(browsable_dir, log_cwd)}"
        )

    verb = _LINK_MODE_VERBS[link_mode]

    for filename, source_dir in files_to_copy:
        if on_file_start:
            on_file_start(filename)

        if not dry_run:
            _place_file(source_dir / filename, browsable_dir / filename, link_mode)

        if log_cwd is not None:
            src = source_dir / filename
            dst = browsable_dir / filename
            _console.print(
                f"{CHECK} {'[dry-run] ' if dry_run else ''}{verb} {display_path(src, log_cwd)} → {display_path(dst, log_cwd)}"
            )

        if on_file_end:
            on_file_end(filename, True)

    return RefreshBrowsableDirResult(copied=len(files_to_copy))
