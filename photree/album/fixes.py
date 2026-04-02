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


# ---------------------------------------------------------------------------
# Aggregated fix runner
# ---------------------------------------------------------------------------


class FixValidationError(ValueError):
    """Raised when fix flag combinations are invalid."""


def validate_fix_flags(
    *,
    fix_id: bool = False,
    new_id: bool = False,
    refresh_browsable: bool,
    refresh_jpeg: bool,
    rm_upstream: bool,
    rm_orphan: bool,
) -> None:
    """Validate fix flag combinations.

    Raises :class:`FixValidationError` when no fix is specified.
    """
    any_fix = (
        fix_id
        or new_id
        or refresh_browsable
        or refresh_jpeg
        or rm_upstream
        or rm_orphan
    )
    if not any_fix:
        raise FixValidationError(
            "No fix specified. Run photree album fix --help for available fixes."
        )


@dataclass(frozen=True)
class FixRefreshBrowsableResult:
    """Aggregated result of refresh-browsable across media sources."""

    heic_copied: int
    mov_copied: int
    jpeg_converted: int
    jpeg_copied: int
    jpeg_skipped: int


@dataclass(frozen=True)
class FixRefreshJpegResult:
    """Aggregated result of refresh-jpeg across media sources."""

    converted: int
    copied: int
    skipped: int


@dataclass(frozen=True)
class FixRmUpstreamResult:
    """Aggregated result of rm-upstream across media sources."""

    heic_jpeg: int
    heic_browsable: int
    heic_rendered: int
    heic_orig: int
    mov_rendered: int
    mov_orig: int


@dataclass(frozen=True)
class FixResult:
    """Aggregated result of all fix operations on a single album."""

    refresh_browsable_result: FixRefreshBrowsableResult | None = None
    refresh_jpeg_result: FixRefreshJpegResult | None = None
    rm_upstream_result: FixRmUpstreamResult | None = None
    rm_orphan_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()


def run_fix(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    log_cwd: Path | None = None,
    refresh_browsable_flag: bool = False,
    refresh_jpeg_flag: bool = False,
    rm_upstream_flag: bool = False,
    rm_orphan_flag: bool = False,
    on_refresh_browsable_stage_start: Callable[[str], None] | None = None,
    on_refresh_browsable_stage_end: Callable[[str], None] | None = None,
    on_refresh_jpeg_file_start: Callable[[str], None] | None = None,
    on_refresh_jpeg_file_end: Callable[[str, bool], None] | None = None,
) -> FixResult:
    """Run selected fix operations on a single album.

    Iterates over all media sources with archives, runs the requested
    operations, and returns aggregated results. Works for both iOS and
    std media sources.
    """
    from ..fs import discover_media_sources

    # Include media sources that have an archive dir on disk
    media_sources = [
        ms
        for ms in discover_media_sources(album_dir)
        if ms.is_ios or (album_dir / ms.archive_dir).is_dir()
    ]

    if not media_sources:
        return FixResult()

    rc_result = None
    rj_result = None
    ru_result = None
    orphan_by_dir: list[tuple[str, tuple[str, ...]]] = []

    if refresh_browsable_flag:
        total_heic = 0
        total_mov = 0
        total_jpeg_converted = 0
        total_jpeg_copied = 0
        total_jpeg_skipped = 0
        for ms in media_sources:
            result = refresh_browsable(
                album_dir,
                ms,
                link_mode=link_mode,
                dry_run=dry_run,
                on_stage_start=on_refresh_browsable_stage_start,
                on_stage_end=on_refresh_browsable_stage_end,
            )
            total_heic += result.heic.copied
            total_mov += result.mov.copied
            total_jpeg_converted += result.jpeg.converted if result.jpeg else 0
            total_jpeg_copied += result.jpeg.copied if result.jpeg else 0
            total_jpeg_skipped += result.jpeg.skipped if result.jpeg else 0
        rc_result = FixRefreshBrowsableResult(
            heic_copied=total_heic,
            mov_copied=total_mov,
            jpeg_converted=total_jpeg_converted,
            jpeg_copied=total_jpeg_copied,
            jpeg_skipped=total_jpeg_skipped,
        )
    elif refresh_jpeg_flag:
        total_converted = 0
        total_copied = 0
        total_skipped = 0
        for ms in media_sources:
            if not (album_dir / ms.img_dir).is_dir():
                continue
            result_jpeg = refresh_jpeg(
                album_dir,
                ms,
                dry_run=dry_run,
                log_cwd=log_cwd,
                on_file_start=on_refresh_jpeg_file_start,
                on_file_end=on_refresh_jpeg_file_end,
            )
            total_converted += result_jpeg.converted
            total_copied += result_jpeg.copied
            total_skipped += result_jpeg.skipped
        rj_result = FixRefreshJpegResult(
            converted=total_converted,
            copied=total_copied,
            skipped=total_skipped,
        )

    if rm_upstream_flag:
        total_heic_jpeg = 0
        total_heic_browsable = 0
        total_heic_rendered = 0
        total_heic_orig = 0
        total_mov_rendered = 0
        total_mov_orig = 0
        for ms in media_sources:
            result_rm = rm_upstream(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd)
            total_heic_jpeg += len(result_rm.heic.removed_jpeg)
            total_heic_browsable += len(result_rm.heic.removed_browsable)
            total_heic_rendered += len(result_rm.heic.removed_rendered)
            total_heic_orig += len(result_rm.heic.removed_orig)
            total_mov_rendered += len(result_rm.mov.removed_rendered)
            total_mov_orig += len(result_rm.mov.removed_orig)
        ru_result = FixRmUpstreamResult(
            heic_jpeg=total_heic_jpeg,
            heic_browsable=total_heic_browsable,
            heic_rendered=total_heic_rendered,
            heic_orig=total_heic_orig,
            mov_rendered=total_mov_rendered,
            mov_orig=total_mov_orig,
        )

    if rm_orphan_flag:
        for ms in media_sources:
            result_orphan = rm_orphan(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd)
            orphan_by_dir.extend(result_orphan.heic.removed_by_dir)
            orphan_by_dir.extend(result_orphan.mov.removed_by_dir)

    return FixResult(
        refresh_browsable_result=rc_result,
        refresh_jpeg_result=rj_result,
        rm_upstream_result=ru_result,
        rm_orphan_removed_by_dir=tuple(orphan_by_dir),
    )
