"""
Rebuild browsable directories from orig/edited archive sources.

The browsable directories contain the "best" version of each media file:
- If an edited version exists, use it
- Otherwise, use the original

This is the same logic used during import (see importer.image_capture),
extracted here so it can be reused by fix commands.
"""

import errno
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from photree.album.store.file_matching import dedup_media_dict
from photree.album.store.media_source import KeyFn
from photree.common.fs import list_files
from photree.common.progress import FileEnd
from photree.foundation.linking import LinkMode

INCOMPLETE_MARKER = ".photree-incomplete"
"""
Name of the file a derived directory holds while it is being rebuilt.

Refresh empties ``{name}-img/``, ``{name}-vid/`` and ``{name}-jpg/`` before
filling them again, so an interrupted or failed rebuild leaves gaps that look
like files the user deleted. The marker is written before the directory is
emptied and removed only once every file is in place: while it is there, the
directory's gaps say nothing about the user's curation.
"""


def mark_incomplete(directory: Path) -> None:
    """Mark *directory*, which must exist, as being rebuilt."""
    (directory / INCOMPLETE_MARKER).touch()


def mark_complete(directory: Path) -> None:
    """Remove the incomplete marker of *directory*, if any."""
    (directory / INCOMPLETE_MARKER).unlink(missing_ok=True)


def is_incomplete(directory: Path) -> bool:
    """Return whether the last rebuild of *directory* failed or was interrupted."""
    return (directory / INCOMPLETE_MARKER).is_file()


def compute_browsable_files(
    orig_dir: Path,
    edit_dir: Path,
    media_extensions: frozenset[str],
    key_fn: KeyFn,
) -> list[tuple[str, Path]]:
    """
    Compute which files should populate a browsable dir: (filename, source_dir) pairs.

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


class CrossDeviceHardlinkError(OSError):
    """A hardlink was asked for between two filesystems, which cannot hold one."""

    def __init__(self, src: Path, dst: Path) -> None:
        """Build the error from the file and the link that could not be made."""
        self.src = src
        self.dst = dst
        super().__init__(
            f"Cannot create hardlink across filesystems: {src} → {dst}. "
            "Use --link-mode symlink instead.",
        )


def place_file(src: Path, dst: Path, link_mode: LinkMode) -> None:
    """
    Create *dst* from *src* as a copy, hardlink or relative symlink.

    Raises :class:`CrossDeviceHardlinkError` when a hardlink is asked for
    across filesystems; other OS errors propagate unchanged.
    """
    match link_mode:
        case LinkMode.COPY:
            shutil.copy(src, dst)
        case LinkMode.HARDLINK:
            try:
                os.link(src, dst)
            except OSError as exc:
                if exc.errno == errno.EXDEV:
                    raise CrossDeviceHardlinkError(src, dst) from exc
                raise
        case LinkMode.SYMLINK:
            rel_src = os.path.relpath(src, dst.parent)
            Path(dst).symlink_to(rel_src)


@dataclass(frozen=True)
class RefreshBrowsableDirResult:
    """The outcome of one browsable directory refresh."""

    copied: int


def refresh_browsable_dir(
    orig_dir: Path,
    edit_dir: Path,
    browsable_dir: Path,
    *,
    media_extensions: frozenset[str],
    key_fn: KeyFn,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_file_start: Callable[[str], None] | None = None,
    on_file_end: FileEnd | None = None,
) -> RefreshBrowsableDirResult:
    """
    Rebuild the browsable directory from the archive.

    The directory is cleared even when the archive is empty or missing, so files of
    deleted media do not survive the refresh. It carries the incomplete marker
    (:data:`INCOMPLETE_MARKER`) until every file is placed, so a failure or an
    interruption midway leaves it marked.
    """
    files_to_copy = compute_browsable_files(
        orig_dir,
        edit_dir,
        media_extensions,
        key_fn,
    )

    if not dry_run:
        _clear_browsable_dir(browsable_dir, create=bool(files_to_copy))

    for filename, source_dir in files_to_copy:
        if on_file_start:
            on_file_start(filename)

        if not dry_run:
            place_file(source_dir / filename, browsable_dir / filename, link_mode)

        if on_file_end:
            on_file_end(filename, success=True)

    if not dry_run:
        mark_complete(browsable_dir)
    return RefreshBrowsableDirResult(copied=len(files_to_copy))


def _clear_browsable_dir(browsable_dir: Path, *, create: bool) -> None:
    """
    Mark *browsable_dir* incomplete and remove its other entries.

    It is created when *create* is set: an empty archive leaves an existing
    browsable dir empty rather than creating one that never existed.
    """
    if create:
        browsable_dir.mkdir(parents=True, exist_ok=True)
    if browsable_dir.is_dir():
        mark_incomplete(browsable_dir)
        for f in browsable_dir.iterdir():
            if f.name != INCOMPLETE_MARKER:
                f.unlink()
