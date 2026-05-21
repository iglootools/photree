"""rm-upstream fix operation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...common.fs import delete_files, list_files
from .. import browsable as browsable_module
from ..store.media_sources import find_files_by_key
from ..store.protocol import IMG_EXTENSIONS, MediaSource
from .helpers import _require_archive


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
    from ...common.fs import file_ext
    from ..store.protocol import (
        CONVERT_TO_JPEG_EXTENSIONS,
        COPY_AS_IS_TO_JPEG_EXTENSIONS,
    )

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

    delete_files(browsable_jpg_dir, jpeg_to_remove, dry_run=dry_run)
    delete_files(browsable_img_dir, browsable_to_remove, dry_run=dry_run)
    delete_files(edit_img_dir, rendered_to_remove, dry_run=dry_run)
    delete_files(orig_img_dir, orig_to_remove, dry_run=dry_run)

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

    delete_files(edit_vid_dir, edit_to_remove, dry_run=dry_run)
    delete_files(orig_vid_dir, orig_to_remove, dry_run=dry_run)

    return RmUpstreamMovResult(
        removed_rendered=tuple(edit_to_remove),
        removed_orig=tuple(orig_to_remove),
    )


def rm_upstream(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
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
        heic=_rm_upstream_heic(album_dir, ms, dry_run=dry_run),
        mov=_rm_upstream_mov(album_dir, ms, dry_run=dry_run),
    )
