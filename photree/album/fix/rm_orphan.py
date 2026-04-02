"""rm-orphan fix operation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...fs import (
    IMG_EXTENSIONS,
    MediaSource,
    VID_EXTENSIONS,
    delete_files,
    list_files,
)
from ...fs.protocol import _KeyFn
from .helpers import _require_archive


def _extract_keys(
    directory: Path,
    media_extensions: frozenset[str],
    key_fn: _KeyFn,
) -> set[str]:
    """Return the set of keys present in an orig directory."""
    from ...fs import file_ext

    return {key_fn(f) for f in list_files(directory) if file_ext(f) in media_extensions}


def _find_orphan_files(
    orig_keys: set[str],
    directory: Path,
    key_fn: _KeyFn,
) -> list[str]:
    """Find files whose key is not in the orig set."""
    return sorted(f for f in list_files(directory) if key_fn(f) not in orig_keys)


@dataclass(frozen=True)
class RmOrphanDirResult:
    """Result of removing orphans for one media type."""

    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def total(self) -> int:
        return sum(len(files) for _, files in self.removed_by_dir)


@dataclass(frozen=True)
class RmOrphanResult:
    """Result of removing orphaned files."""

    heic: RmOrphanDirResult
    mov: RmOrphanDirResult


def _rm_orphans_in_dir(
    orig_keys: set[str],
    directory: Path,
    key_fn: _KeyFn,
    *,
    dry_run: bool,
) -> tuple[str, tuple[str, ...]] | None:
    """Remove orphan files from a single directory. Returns (dir_name, removed) or None."""
    if not directory.is_dir():
        return None
    orphans = _find_orphan_files(orig_keys, directory, key_fn)
    if not orphans:
        return None
    delete_files(directory, orphans, dry_run=dry_run)
    return (directory.name, tuple(orphans))


def _rm_orphans_in_dirs(
    orig_keys: set[str],
    directories: tuple[Path, ...],
    key_fn: _KeyFn,
    *,
    dry_run: bool,
) -> RmOrphanDirResult:
    """Remove files from directories whose key has no orig counterpart."""
    return RmOrphanDirResult(
        removed_by_dir=tuple(
            result
            for d in directories
            if (result := _rm_orphans_in_dir(orig_keys, d, key_fn, dry_run=dry_run))
            is not None
        )
    )


def rm_orphan(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> RmOrphanResult:
    """Remove edited and browsable files that have no corresponding orig file.

    Works for both iOS and std media sources.

    Images: files in edit-img, {name}-img, and {name}-jpg whose
    key is not present in orig-img are deleted.

    Videos: files in edit-vid and {name}-vid whose key is not
    present in orig-vid are deleted.
    """
    _require_archive(album_dir, ms)
    key_fn = ms.key_fn

    heic_keys = _extract_keys(album_dir / ms.orig_img_dir, IMG_EXTENSIONS, key_fn)
    mov_keys = _extract_keys(album_dir / ms.orig_vid_dir, VID_EXTENSIONS, key_fn)

    return RmOrphanResult(
        heic=_rm_orphans_in_dirs(
            heic_keys,
            (
                album_dir / ms.edit_img_dir,
                album_dir / ms.img_dir,
                album_dir / ms.jpg_dir,
            ),
            key_fn,
            dry_run=dry_run,
        ),
        mov=_rm_orphans_in_dirs(
            mov_keys,
            (
                album_dir / ms.edit_vid_dir,
                album_dir / ms.vid_dir,
            ),
            key_fn,
            dry_run=dry_run,
        ),
    )
