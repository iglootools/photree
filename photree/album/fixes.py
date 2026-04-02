"""Generic fix operations for all album media source types.

Unlike :mod:`ios_fixes` which requires iOS media sources, these operations
work with both iOS and std media sources.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from ..common.formatting import CHECK

from . import browsable as browsable_module
from . import jpeg
from .browsable import RefreshBrowsableDirResult
from .jpeg import RefreshResult, convert_single_file
from ..fs import (
    IMG_EXTENSIONS,
    MediaSource,
    LinkMode,
    VID_EXTENSIONS,
    delete_files,
    display_path,
    list_files,
)
from ..fs.media import find_files_by_key
from ..fs.protocol import _KeyFn

_console = Console(highlight=False)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# refresh-jpeg
# ---------------------------------------------------------------------------


def refresh_jpeg(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
    on_file_start: Callable[[str], None] | None = None,
    on_file_end: Callable[[str, bool], None] | None = None,
) -> RefreshResult:
    """Refresh ``{name}-jpg/`` from ``{name}-img/``.

    Works for both iOS and std media sources. Raises
    :class:`FileNotFoundError` if the source image directory does not exist.
    """
    src_dir = album_dir / ms.img_dir
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Directory not found: {src_dir}")

    # When progress callbacks are provided, skip per-file verbose logging —
    # the progress bar already provides feedback.
    jpeg_log_cwd = log_cwd if on_file_end is None else None
    return jpeg.refresh_jpeg_dir(
        src_dir,
        album_dir / ms.jpg_dir,
        dry_run=dry_run,
        log_cwd=jpeg_log_cwd,
        convert_file=convert_file,
        on_file_start=on_file_start,
        on_file_end=on_file_end,
    )


# ---------------------------------------------------------------------------
# refresh-browsable
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RefreshBrowsableResult:
    """Result of refreshing all browsable directories for a media source."""

    heic: RefreshBrowsableDirResult
    mov: RefreshBrowsableDirResult
    jpeg: RefreshResult | None


def refresh_browsable(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    log_cwd: Path | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
) -> RefreshBrowsableResult:
    """Delete browsable dirs, rebuild img/vid from archive, then jpeg.

    Works for both iOS and std media sources. Raises
    :class:`FileNotFoundError` for legacy std sources without archives.

    Stage callbacks fire for: ``delete``, ``refresh-heic``, ``refresh-mov``,
    ``refresh-jpeg``.
    """
    _require_archive(album_dir, ms)

    browsable_img = album_dir / ms.img_dir
    browsable_vid = album_dir / ms.vid_dir
    browsable_jpg = album_dir / ms.jpg_dir

    # Delete all browsable directories
    if on_stage_start:
        on_stage_start("delete")
    for d in (browsable_img, browsable_vid, browsable_jpg):
        _delete_dir(d, dry_run=dry_run, log_cwd=log_cwd)
    if on_stage_end:
        on_stage_end("delete")

    # Rebuild browsable img
    if on_stage_start:
        on_stage_start("refresh-heic")
    heic_result = browsable_module.refresh_browsable_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        browsable_img,
        media_extensions=IMG_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    if on_stage_end:
        on_stage_end("refresh-heic")

    # Rebuild browsable vid
    if on_stage_start:
        on_stage_start("refresh-mov")
    mov_result = browsable_module.refresh_browsable_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        browsable_vid,
        media_extensions=VID_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    if on_stage_end:
        on_stage_end("refresh-mov")

    # Rebuild browsable jpg if browsable img was created
    has_img = browsable_img.is_dir() if not dry_run else heic_result.copied > 0
    if on_stage_start:
        on_stage_start("refresh-jpeg")
    jpeg_result = (
        jpeg.refresh_jpeg_dir(
            browsable_img,
            browsable_jpg,
            dry_run=dry_run,
            convert_file=convert_file,
        )
        if has_img
        else None
    )
    if on_stage_end:
        on_stage_end("refresh-jpeg")

    return RefreshBrowsableResult(heic=heic_result, mov=mov_result, jpeg=jpeg_result)


# ---------------------------------------------------------------------------
# rm-orphan
# ---------------------------------------------------------------------------


def _extract_keys(
    directory: Path,
    media_extensions: frozenset[str],
    key_fn: _KeyFn,
) -> set[str]:
    """Return the set of keys present in an orig directory."""
    from ..fs import file_ext

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
    log_cwd: Path | None,
) -> tuple[str, tuple[str, ...]] | None:
    """Remove orphan files from a single directory. Returns (dir_name, removed) or None."""
    if not directory.is_dir():
        return None
    orphans = _find_orphan_files(orig_keys, directory, key_fn)
    if not orphans:
        return None
    delete_files(directory, orphans, dry_run=dry_run, log_cwd=log_cwd)
    return (directory.name, tuple(orphans))


def _rm_orphans_in_dirs(
    orig_keys: set[str],
    directories: tuple[Path, ...],
    key_fn: _KeyFn,
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> RmOrphanDirResult:
    """Remove files from directories whose key has no orig counterpart."""
    return RmOrphanDirResult(
        removed_by_dir=tuple(
            result
            for d in directories
            if (
                result := _rm_orphans_in_dir(
                    orig_keys, d, key_fn, dry_run=dry_run, log_cwd=log_cwd
                )
            )
            is not None
        )
    )


def rm_orphan(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
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
            log_cwd=log_cwd,
        ),
        mov=_rm_orphans_in_dirs(
            mov_keys,
            (
                album_dir / ms.edit_vid_dir,
                album_dir / ms.vid_dir,
            ),
            key_fn,
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
    )


# ---------------------------------------------------------------------------
# rm-upstream
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RmUpstreamHeicResult:
    """Result of propagating image deletions."""

    removed_jpeg: tuple[str, ...]
    removed_browsable: tuple[str, ...]
    removed_rendered: tuple[str, ...]
    removed_orig: tuple[str, ...]


@dataclass(frozen=True)
class RmUpstreamMovResult:
    """Result of propagating video deletions."""

    removed_rendered: tuple[str, ...]
    removed_orig: tuple[str, ...]


@dataclass(frozen=True)
class RmUpstreamResult:
    """Result of propagating deletions from browsable dirs to archive dirs."""

    heic: RmUpstreamHeicResult
    mov: RmUpstreamMovResult


def _expected_jpeg_name(heic_filename: str) -> str | None:
    """Return the expected JPEG filename for a browsable img file."""
    from ..fs import CONVERT_TO_JPEG_EXTENSIONS, COPY_AS_IS_TO_JPEG_EXTENSIONS, file_ext

    ext = file_ext(heic_filename)
    if ext in CONVERT_TO_JPEG_EXTENSIONS:
        return Path(heic_filename).with_suffix(".jpg").name
    elif ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
        return heic_filename
    else:
        return None


def _rm_upstream_heic(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> RmUpstreamHeicResult:
    """Propagate image deletions through the full chain.

    Detects deletions from two entry points:
    - {name}-jpg: files missing relative to {name}-img
    - {name}-img: files missing relative to what orig/edited would produce

    Both are merged and propagated to all upstream dirs.
    """
    _require_archive(album_dir, ms)
    key_fn = ms.key_fn

    browsable_img_dir = album_dir / ms.img_dir
    browsable_jpg_dir = album_dir / ms.jpg_dir
    orig_img_dir = album_dir / ms.orig_img_dir
    edit_img_dir = album_dir / ms.edit_img_dir

    browsable_img_files = set(list_files(browsable_img_dir))
    browsable_jpg_files = set(list_files(browsable_jpg_dir))

    # Source 1: files deleted from {name}-jpg (relative to {name}-img)
    keys_from_jpeg = {
        key_fn(f)
        for f in browsable_img_files
        if (jpeg_name := _expected_jpeg_name(f)) is not None
        and jpeg_name not in browsable_jpg_files
    }

    # Source 2: files deleted from {name}-img (relative to orig/edited)
    expected_browsable = {
        filename
        for filename, _source_dir in browsable_module.compute_browsable_files(
            orig_img_dir, edit_img_dir, IMG_EXTENSIONS, key_fn
        )
    }
    keys_from_heic = {
        key_fn(f) for f in expected_browsable if f not in browsable_img_files
    }

    keys_to_remove = keys_from_jpeg | keys_from_heic

    if not keys_to_remove:
        return RmUpstreamHeicResult(
            removed_jpeg=(),
            removed_browsable=(),
            removed_rendered=(),
            removed_orig=(),
        )

    # Propagate to all directories
    jpeg_to_remove = find_files_by_key(keys_to_remove, browsable_jpg_dir, key_fn)
    browsable_to_remove = find_files_by_key(keys_to_remove, browsable_img_dir, key_fn)
    rendered_to_remove = find_files_by_key(keys_to_remove, edit_img_dir, key_fn)
    orig_to_remove = find_files_by_key(keys_to_remove, orig_img_dir, key_fn)

    delete_files(browsable_jpg_dir, jpeg_to_remove, dry_run=dry_run, log_cwd=log_cwd)
    delete_files(
        browsable_img_dir, browsable_to_remove, dry_run=dry_run, log_cwd=log_cwd
    )
    delete_files(edit_img_dir, rendered_to_remove, dry_run=dry_run, log_cwd=log_cwd)
    delete_files(orig_img_dir, orig_to_remove, dry_run=dry_run, log_cwd=log_cwd)

    return RmUpstreamHeicResult(
        removed_jpeg=tuple(jpeg_to_remove),
        removed_browsable=tuple(browsable_to_remove),
        removed_rendered=tuple(rendered_to_remove),
        removed_orig=tuple(orig_to_remove),
    )


def _rm_upstream_mov(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> RmUpstreamMovResult:
    """Propagate video deletions from browsable to archive.

    Files in orig-vid whose key is not present in {name}-vid are removed
    from edit-vid and orig-vid.  The comparison is key-based (not by exact
    filename) so that edited videos (e.g. ``IMG_E0001.MOV``) are correctly
    matched to their originals (``IMG_0001.MOV``).
    """
    _require_archive(album_dir, ms)
    key_fn = ms.key_fn

    orig_vid_dir = album_dir / ms.orig_vid_dir
    edit_vid_dir = album_dir / ms.edit_vid_dir
    browsable_vid_dir = album_dir / ms.vid_dir

    orig_files = list_files(orig_vid_dir)
    browsable_keys = {key_fn(f) for f in list_files(browsable_vid_dir)}

    keys_to_remove = {key_fn(f) for f in orig_files if key_fn(f) not in browsable_keys}

    if not keys_to_remove:
        return RmUpstreamMovResult(removed_rendered=(), removed_orig=())

    edit_to_remove = find_files_by_key(keys_to_remove, edit_vid_dir, key_fn)
    orig_to_remove = find_files_by_key(keys_to_remove, orig_vid_dir, key_fn)

    delete_files(edit_vid_dir, edit_to_remove, dry_run=dry_run, log_cwd=log_cwd)
    delete_files(orig_vid_dir, orig_to_remove, dry_run=dry_run, log_cwd=log_cwd)

    return RmUpstreamMovResult(
        removed_rendered=tuple(edit_to_remove),
        removed_orig=tuple(orig_to_remove),
    )


def rm_upstream(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> RmUpstreamResult:
    """Propagate deletions from browsable dirs to archive dirs.

    Works for both iOS and std media sources.

    Images: deletions detected from {name}-jpg or {name}-img are
    propagated to {name}-jpg, {name}-img, edit-img, and orig-img.

    Videos: files missing from {name}-vid (relative to orig-vid) are
    removed from edit-vid and orig-vid.
    """
    _require_archive(album_dir, ms)
    return RmUpstreamResult(
        heic=_rm_upstream_heic(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd),
        mov=_rm_upstream_mov(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd),
    )
