"""Fix operations for iOS albums.

Each function orchestrates a specific fix: deleting stale data, rebuilding
from sources, and returning a structured result. CLI concerns (progress bars,
output formatting, exit codes) are handled by the caller.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from ..uiconventions import CHECK

from . import combined as combined_module
from . import jpeg
from .combined import RefreshMainDirResult
from .jpeg import RefreshResult, convert_single_file
from ..fs import (
    CONVERT_TO_JPEG_EXTENSIONS,
    COPY_AS_IS_TO_JPEG_EXTENSIONS,
    MediaSource,
    IOS_IMG_EXTENSIONS,
    LinkMode,
    IOS_VID_EXTENSIONS,
    PICTURE_PRIORITY_EXTENSIONS,
    SIDECAR_EXTENSIONS,
    delete_files,
    display_path,
    find_files_by_number,
    list_files,
    move_files,
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


@dataclass(frozen=True)
class RefreshCombinedResult:
    """Result of refreshing all main directories."""

    heic: RefreshMainDirResult
    mov: RefreshMainDirResult
    jpeg: RefreshResult | None


def refresh_combined(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    log_cwd: Path | None = None,
    convert_file: Callable[..., Path | None] = convert_single_file,
    on_stage_start: Callable[[str], None] | None = None,
    on_stage_end: Callable[[str], None] | None = None,
) -> RefreshCombinedResult:
    """Delete main dirs, rebuild main-img/vid, then jpeg if applicable.

    Stage callbacks fire for: ``delete``, ``refresh-heic``, ``refresh-mov``,
    ``refresh-jpeg``.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    main_img = album_dir / ms.img_dir
    main_vid = album_dir / ms.vid_dir
    main_jpg = album_dir / ms.jpg_dir

    # Delete all main directories
    if on_stage_start:
        on_stage_start("delete")
    for d in (main_img, main_vid, main_jpg):
        _delete_dir(d, dry_run=dry_run, log_cwd=log_cwd)
    if on_stage_end:
        on_stage_end("delete")

    # Rebuild main-img
    if on_stage_start:
        on_stage_start("refresh-heic")
    heic_result = combined_module.refresh_main_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        main_img,
        media_extensions=IOS_IMG_EXTENSIONS,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    if on_stage_end:
        on_stage_end("refresh-heic")

    # Rebuild main-vid
    if on_stage_start:
        on_stage_start("refresh-mov")
    mov_result = combined_module.refresh_main_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        main_vid,
        media_extensions=IOS_VID_EXTENSIONS,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    if on_stage_end:
        on_stage_end("refresh-mov")

    # Rebuild main-jpg if main-img was created
    has_main_img = main_img.is_dir() if not dry_run else heic_result.copied > 0
    if on_stage_start:
        on_stage_start("refresh-jpeg")
    jpeg_result = (
        jpeg.refresh_jpeg_dir(
            main_img,
            main_jpg,
            dry_run=dry_run,
            convert_file=convert_file,
        )
        if has_main_img
        else None
    )
    if on_stage_end:
        on_stage_end("refresh-jpeg")

    return RefreshCombinedResult(heic=heic_result, mov=mov_result, jpeg=jpeg_result)


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
    """Refresh main-jpg/ from main-img/ (iOS media source only).

    Delegates to :func:`fixes.refresh_jpeg` with an iOS assertion.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    from .fixes import refresh_jpeg as generic_refresh_jpeg

    return generic_refresh_jpeg(
        album_dir,
        ms,
        dry_run=dry_run,
        log_cwd=log_cwd,
        convert_file=convert_file,
        on_file_start=on_file_start,
        on_file_end=on_file_end,
    )


# ---------------------------------------------------------------------------
# rm-upstream
# ---------------------------------------------------------------------------


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _img_number(filename: str) -> str:
    return "".join(c for c in filename if c.isdigit())


def _expected_jpeg_name(heic_filename: str) -> str | None:
    """Return the expected JPEG filename for a main-img file."""
    ext = _ext(heic_filename)
    if ext in CONVERT_TO_JPEG_EXTENSIONS:
        return Path(heic_filename).with_suffix(".jpg").name
    elif ext in COPY_AS_IS_TO_JPEG_EXTENSIONS:
        return heic_filename
    else:
        return None


@dataclass(frozen=True)
class RmUpstreamHeicResult:
    """Result of propagating image deletions."""

    removed_jpeg: tuple[str, ...]
    removed_combined: tuple[str, ...]
    removed_rendered: tuple[str, ...]
    removed_orig: tuple[str, ...]


@dataclass(frozen=True)
class RmUpstreamMovResult:
    """Result of propagating video deletions."""

    removed_rendered: tuple[str, ...]
    removed_orig: tuple[str, ...]


@dataclass(frozen=True)
class RmUpstreamResult:
    """Result of propagating deletions from browsing dirs to upstream dirs."""

    heic: RmUpstreamHeicResult
    mov: RmUpstreamMovResult


def _rm_upstream_heic(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> RmUpstreamHeicResult:
    """Propagate image deletions through the full chain.

    Detects deletions from two entry points:
    - main-jpg: files missing relative to main-img
    - main-img: files missing relative to what orig/edited would produce

    Both are merged and propagated to all upstream dirs.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    main_img_dir = album_dir / ms.img_dir
    main_jpg_dir = album_dir / ms.jpg_dir
    orig_img_dir = album_dir / ms.orig_img_dir
    edit_img_dir = album_dir / ms.edit_img_dir

    main_img_files = set(list_files(main_img_dir))
    main_jpg_files = set(list_files(main_jpg_dir))

    # Source 1: files deleted from main-jpg (relative to main-img)
    numbers_from_jpeg = {
        _img_number(f)
        for f in main_img_files
        if (jpeg_name := _expected_jpeg_name(f)) is not None
        and jpeg_name not in main_jpg_files
    }

    # Source 2: files deleted from main-img (relative to orig/edited)
    expected_main = {
        filename
        for filename, _source_dir in combined_module.compute_main_files(
            orig_img_dir, edit_img_dir, IOS_IMG_EXTENSIONS
        )
    }
    numbers_from_heic = {
        _img_number(f) for f in expected_main if f not in main_img_files
    }

    numbers_to_remove = numbers_from_jpeg | numbers_from_heic

    if not numbers_to_remove:
        return RmUpstreamHeicResult(
            removed_jpeg=(), removed_combined=(), removed_rendered=(), removed_orig=()
        )

    # Delete from main-jpg
    jpeg_to_remove = find_files_by_number(numbers_to_remove, main_jpg_dir)
    delete_files(main_jpg_dir, jpeg_to_remove, dry_run=dry_run, log_cwd=log_cwd)

    # Delete from main-img
    heic_to_remove = find_files_by_number(numbers_to_remove, main_img_dir)
    delete_files(main_img_dir, heic_to_remove, dry_run=dry_run, log_cwd=log_cwd)

    # Delete from edit-img and orig-img
    edit_to_remove = find_files_by_number(numbers_to_remove, edit_img_dir)
    delete_files(edit_img_dir, edit_to_remove, dry_run=dry_run, log_cwd=log_cwd)

    orig_to_remove = find_files_by_number(numbers_to_remove, orig_img_dir)
    delete_files(orig_img_dir, orig_to_remove, dry_run=dry_run, log_cwd=log_cwd)

    return RmUpstreamHeicResult(
        removed_jpeg=tuple(jpeg_to_remove),
        removed_combined=tuple(heic_to_remove),
        removed_rendered=tuple(edit_to_remove),
        removed_orig=tuple(orig_to_remove),
    )


def _rm_upstream_mov(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> RmUpstreamMovResult:
    """Propagate deletions from main-vid to edit-vid, orig-vid.

    Files missing from main-vid (relative to orig-vid/edit-vid) are treated
    as intentional deletions. The corresponding files are removed from upstream dirs.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    main_vid_dir = album_dir / ms.vid_dir
    orig_vid_dir = album_dir / ms.orig_vid_dir

    main_vid_files = set(list_files(main_vid_dir))
    orig_vid_files = list_files(orig_vid_dir)

    # Find image numbers present in orig-vid but missing from main-vid
    main_numbers = {_img_number(f) for f in main_vid_files}
    orig_numbers = {
        _img_number(f): f for f in orig_vid_files if _ext(f) in IOS_VID_EXTENSIONS
    }
    numbers_to_remove = {num for num in orig_numbers if num not in main_numbers}

    if not numbers_to_remove:
        return RmUpstreamMovResult(removed_rendered=(), removed_orig=())

    # Delete matching files from edit-vid and orig-vid (by image number)
    edit_to_remove = find_files_by_number(
        numbers_to_remove, album_dir / ms.edit_vid_dir
    )
    delete_files(
        album_dir / ms.edit_vid_dir,
        edit_to_remove,
        dry_run=dry_run,
        log_cwd=log_cwd,
    )

    orig_to_remove = find_files_by_number(
        numbers_to_remove, album_dir / ms.orig_vid_dir
    )
    delete_files(
        album_dir / ms.orig_vid_dir,
        orig_to_remove,
        dry_run=dry_run,
        log_cwd=log_cwd,
    )

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
    """Propagate deletions from browsing dirs to upstream dirs.

    Images: deletions detected from main-jpg or main-img are
    propagated to main-jpg, main-img, edit-img, and orig-img.

    Videos: files missing from main-vid (relative to orig-vid) are
    removed from edit-vid and orig-vid.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    return RmUpstreamResult(
        heic=_rm_upstream_heic(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd),
        mov=_rm_upstream_mov(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd),
    )


# ---------------------------------------------------------------------------
# rm-orphan
# ---------------------------------------------------------------------------


def _orig_numbers(directory: Path, media_extensions: frozenset[str]) -> set[str]:
    """Return the set of image numbers present in an orig directory."""
    return {
        _img_number(f) for f in list_files(directory) if _ext(f) in media_extensions
    }


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
    orig_numbers: set[str],
    directory: Path,
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> tuple[str, tuple[str, ...]] | None:
    """Remove orphan files from a single directory. Returns (dir_name, removed) or None."""
    if not directory.is_dir():
        return None
    orphans = _find_orphan_files(orig_numbers, directory)
    if not orphans:
        return None
    delete_files(directory, orphans, dry_run=dry_run, log_cwd=log_cwd)
    return (directory.name, tuple(orphans))


def _rm_orphans_in_dirs(
    orig_numbers: set[str],
    directories: tuple[Path, ...],
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> RmOrphanDirResult:
    """Remove files from directories whose image number has no orig counterpart."""
    return RmOrphanDirResult(
        removed_by_dir=tuple(
            result
            for d in directories
            if (
                result := _rm_orphans_in_dir(
                    orig_numbers, d, dry_run=dry_run, log_cwd=log_cwd
                )
            )
            is not None
        )
    )


def _find_orphan_files(orig_numbers: set[str], directory: Path) -> list[str]:
    """Find files whose image number is not in the orig set."""
    return sorted(
        f for f in list_files(directory) if _img_number(f) not in orig_numbers
    )


def rm_orphan(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> RmOrphanResult:
    """Remove edited and main files that have no corresponding orig file.

    Images: files in edit-img, main-img, and main-jpg whose
    image number is not present in orig-img are deleted.

    Videos: files in edit-vid and main-vid whose image number is not
    present in orig-vid are deleted.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    heic_numbers = _orig_numbers(album_dir / ms.orig_img_dir, IOS_IMG_EXTENSIONS)
    mov_numbers = _orig_numbers(album_dir / ms.orig_vid_dir, IOS_VID_EXTENSIONS)

    return RmOrphanResult(
        heic=_rm_orphans_in_dirs(
            heic_numbers,
            (
                album_dir / ms.edit_img_dir,
                album_dir / ms.img_dir,
                album_dir / ms.jpg_dir,
            ),
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
        mov=_rm_orphans_in_dirs(
            mov_numbers,
            (
                album_dir / ms.edit_vid_dir,
                album_dir / ms.vid_dir,
            ),
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
    )


# ---------------------------------------------------------------------------
# rm-orphan-sidecar
# ---------------------------------------------------------------------------


def _find_orphan_sidecars(directory: Path) -> list[str]:
    """Find AAE files whose image number has no matching media file."""
    files = list_files(directory)
    media_numbers = {_img_number(f) for f in files if _is_media(f)}
    return sorted(
        f
        for f in files
        if _ext(f) in SIDECAR_EXTENSIONS and _img_number(f) not in media_numbers
    )


def _is_media(filename: str) -> bool:
    ext = _ext(filename)
    return ext in IOS_IMG_EXTENSIONS or ext in IOS_VID_EXTENSIONS


@dataclass(frozen=True)
class RmOrphanSidecarResult:
    """Result of removing orphan sidecars."""

    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def total(self) -> int:
        return sum(len(files) for _, files in self.removed_by_dir)


def rm_orphan_sidecar(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> RmOrphanSidecarResult:
    """Remove AAE sidecar files that have no matching media file.

    Scans orig-img/, edit-img/, orig-vid/, and edit-vid/.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    directories = (
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
    )

    results: list[tuple[str, tuple[str, ...]]] = []
    for d in directories:
        if not d.is_dir():
            continue
        orphans = _find_orphan_sidecars(d)
        if not orphans:
            continue
        delete_files(d, orphans, dry_run=dry_run, log_cwd=log_cwd)
        results.append((d.name, tuple(orphans)))

    return RmOrphanSidecarResult(removed_by_dir=tuple(results))


# ---------------------------------------------------------------------------
# prefer-higher-quality-when-dups
# ---------------------------------------------------------------------------


def _find_non_heic_dups_in_dir(
    directory: Path, media_extensions: frozenset[str]
) -> list[str]:
    """Find non-HEIC media files that share an image number with a HEIC file."""
    files = list_files(directory)
    media_by_number: dict[str, list[str]] = {}
    for f in files:
        if _ext(f) in media_extensions:
            media_by_number.setdefault(_img_number(f), []).append(f)

    return sorted(
        non_heic
        for candidates in media_by_number.values()
        if any(_ext(f) in PICTURE_PRIORITY_EXTENSIONS for f in candidates)
        for non_heic in candidates
        if _ext(non_heic) not in PICTURE_PRIORITY_EXTENSIONS
    )


@dataclass(frozen=True)
class PreferHigherQualityResult:
    """Result of removing non-HEIC duplicates."""

    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def total(self) -> int:
        return sum(len(files) for _, files in self.removed_by_dir)


def prefer_higher_quality_when_dups(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> PreferHigherQualityResult:
    """Delete lower-quality duplicates when multiple formats exist for the same number.

    Scans all image subdirectories. For each image number that has multiple
    format variants, keeps the highest-quality file (DNG > HEIC > JPG/PNG)
    and deletes the rest.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    directories = (
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        album_dir / ms.jpg_dir,
    )

    def _process_dir(d: Path) -> tuple[str, tuple[str, ...]] | None:
        if not d.is_dir():
            return None
        dups = _find_non_heic_dups_in_dir(d, IOS_IMG_EXTENSIONS)
        if not dups:
            return None
        delete_files(d, dups, dry_run=dry_run, log_cwd=log_cwd)
        return (d.name, tuple(dups))

    return PreferHigherQualityResult(
        removed_by_dir=tuple(
            result for d in directories if (result := _process_dir(d)) is not None
        )
    )


# ---------------------------------------------------------------------------
# miscategorized files (rm / mv)
# ---------------------------------------------------------------------------


def _file_prefix(filename: str) -> str:
    """Extract the prefix category: 'E' (edited), 'O' (edited sidecar), '' (original)."""
    lower = filename.lower()
    if lower.startswith("img_e"):
        return "E"
    elif lower.startswith("img_o"):
        return "O"
    else:
        return ""


def _find_miscategorized(
    orig_dir: Path,
    edit_dir: Path,
) -> tuple[list[str], list[str]]:
    """Find miscategorized files.

    Returns (edited_in_orig, orig_in_edit) — files that are in the wrong dir.
    Edited files are those with IMG_E or IMG_O prefix.
    Original files are those without E/O prefix.
    """
    orig_files = list_files(orig_dir)
    edit_files = list_files(edit_dir)

    edited_in_orig = sorted(f for f in orig_files if _file_prefix(f) in ("E", "O"))
    orig_in_edit = sorted(f for f in edit_files if _file_prefix(f) == "")

    return edited_in_orig, orig_in_edit


@dataclass(frozen=True)
class MiscategorizedDirResult:
    """Result of fixing miscategorized files for one media type pair."""

    fixed_from_orig: tuple[str, ...]
    fixed_from_rendered: tuple[str, ...]


@dataclass(frozen=True)
class MiscategorizedResult:
    """Result of fixing miscategorized files."""

    heic: MiscategorizedDirResult
    mov: MiscategorizedDirResult

    @property
    def total(self) -> int:
        return (
            len(self.heic.fixed_from_orig)
            + len(self.heic.fixed_from_rendered)
            + len(self.mov.fixed_from_orig)
            + len(self.mov.fixed_from_rendered)
        )


def _filter_safe(files: list[str], target_dir: Path) -> list[str]:
    """Keep only files that already exist in the target directory."""
    target_files = set(list_files(target_dir))
    return [f for f in files if f in target_files]


def _fix_miscategorized_pair(
    orig_dir: Path,
    edit_dir: Path,
    *,
    action: str,
    dry_run: bool,
    log_cwd: Path | None,
) -> MiscategorizedDirResult:
    """Fix miscategorized files for one orig/edit pair.

    action is 'rm' (delete), 'rm-safe' (delete only if present in correct dir),
    or 'mv' (move to correct dir).
    """
    edited_in_orig, orig_in_edit = _find_miscategorized(orig_dir, edit_dir)

    if action == "rm-safe":
        edited_in_orig = _filter_safe(edited_in_orig, edit_dir)
        orig_in_edit = _filter_safe(orig_in_edit, orig_dir)

    if action in ("rm", "rm-safe"):
        delete_files(orig_dir, edited_in_orig, dry_run=dry_run, log_cwd=log_cwd)
        delete_files(edit_dir, orig_in_edit, dry_run=dry_run, log_cwd=log_cwd)
    elif action == "mv":
        move_files(orig_dir, edit_dir, edited_in_orig, dry_run=dry_run, log_cwd=log_cwd)
        move_files(edit_dir, orig_dir, orig_in_edit, dry_run=dry_run, log_cwd=log_cwd)

    return MiscategorizedDirResult(
        fixed_from_orig=tuple(edited_in_orig),
        fixed_from_rendered=tuple(orig_in_edit),
    )


def rm_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> MiscategorizedResult:
    """Delete files that are in the wrong directory (edited in orig or vice versa)."""
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    return MiscategorizedResult(
        heic=_fix_miscategorized_pair(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            action="rm",
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
        mov=_fix_miscategorized_pair(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            action="rm",
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
    )


def rm_miscategorized_safe(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> MiscategorizedResult:
    """Delete miscategorized files only if they already exist in the correct directory."""
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    return MiscategorizedResult(
        heic=_fix_miscategorized_pair(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            action="rm-safe",
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
        mov=_fix_miscategorized_pair(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            action="rm-safe",
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
    )


def mv_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
    log_cwd: Path | None = None,
) -> MiscategorizedResult:
    """Move files that are in the wrong directory to the correct one."""
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    return MiscategorizedResult(
        heic=_fix_miscategorized_pair(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            action="mv",
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
        mov=_fix_miscategorized_pair(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            action="mv",
            dry_run=dry_run,
            log_cwd=log_cwd,
        ),
    )


# ---------------------------------------------------------------------------
# Aggregated fix-ios runner
# ---------------------------------------------------------------------------


class FixIosValidationError(ValueError):
    """Raised when fix-ios flag combinations are invalid."""


def validate_fix_flags(
    *,
    refresh_combined: bool,
    refresh_jpeg: bool,
    rm_upstream: bool,
    rm_orphan: bool,
    rm_orphan_sidecar: bool,
    prefer_higher_quality_when_dups: bool,
    rm_miscategorized: bool,
    rm_miscategorized_safe: bool,
    mv_miscategorized: bool,
) -> None:
    """Validate fix-ios flag combinations.

    Raises :class:`FixIosValidationError` on invalid combinations.
    """
    miscat_flags = sum([rm_miscategorized, rm_miscategorized_safe, mv_miscategorized])
    if miscat_flags > 1:
        raise FixIosValidationError(
            "--rm-miscategorized, --rm-miscategorized-safe, and --mv-miscategorized "
            "are mutually exclusive."
        )

    any_fix = (
        refresh_combined
        or refresh_jpeg
        or rm_upstream
        or rm_orphan
        or rm_orphan_sidecar
        or prefer_higher_quality_when_dups
        or miscat_flags > 0
    )
    if not any_fix:
        raise FixIosValidationError(
            "No fix specified. Run photree album fix-ios --help for available fixes."
        )


@dataclass(frozen=True)
class FixIosRefreshCombinedResult:
    """Aggregated result of refresh-combined across media sources."""

    heic_copied: int
    mov_copied: int
    jpeg_converted: int
    jpeg_copied: int
    jpeg_skipped: int


@dataclass(frozen=True)
class FixIosRefreshJpegResult:
    """Aggregated result of refresh-jpeg across media sources."""

    converted: int
    copied: int
    skipped: int


@dataclass(frozen=True)
class FixIosRmUpstreamResult:
    """Aggregated result of rm-upstream across media sources."""

    heic_jpeg: int
    heic_combined: int
    heic_rendered: int
    heic_orig: int
    mov_rendered: int
    mov_orig: int


@dataclass(frozen=True)
class FixIosMiscategorizedResult:
    """Aggregated result of miscategorized fix across media sources."""

    action: str
    heic_from_orig: int
    heic_from_rendered: int
    mov_from_orig: int
    mov_from_rendered: int


@dataclass(frozen=True)
class FixIosResult:
    """Aggregated result of all fix-ios operations on a single album."""

    refresh_combined_result: FixIosRefreshCombinedResult | None = None
    refresh_jpeg_result: FixIosRefreshJpegResult | None = None
    rm_upstream_result: FixIosRmUpstreamResult | None = None
    rm_orphan_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()
    rm_orphan_sidecar_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()
    prefer_higher_quality_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()
    miscategorized_result: FixIosMiscategorizedResult | None = None


# Aliases for use within run_fix_ios where parameter names shadow module functions
_do_rm_upstream = rm_upstream
_do_rm_orphan = rm_orphan
_do_rm_orphan_sidecar = rm_orphan_sidecar
_do_prefer_higher_quality = prefer_higher_quality_when_dups
_do_rm_miscategorized = rm_miscategorized
_do_rm_miscategorized_safe = rm_miscategorized_safe
_do_mv_miscategorized = mv_miscategorized


def run_fix_ios(
    album_dir: Path,
    *,
    link_mode: LinkMode,
    dry_run: bool,
    log_cwd: Path | None = None,
    refresh_combined_flag: bool = False,
    refresh_jpeg_flag: bool = False,
    rm_upstream: bool = False,
    rm_orphan: bool = False,
    rm_orphan_sidecar: bool = False,
    prefer_higher_quality_when_dups: bool = False,
    rm_miscategorized: bool = False,
    rm_miscategorized_safe: bool = False,
    mv_miscategorized: bool = False,
    on_refresh_combined_stage_start: Callable[[str], None] | None = None,
    on_refresh_combined_stage_end: Callable[[str], None] | None = None,
    on_refresh_jpeg_file_start: Callable[[str], None] | None = None,
    on_refresh_jpeg_file_end: Callable[[str, bool], None] | None = None,
) -> FixIosResult:
    """Run selected fix-ios operations on a single album.

    Iterates over all iOS media sources, runs the requested operations,
    and returns aggregated results. The caller handles output formatting
    and progress bars via the optional callbacks.
    """
    from ..fs import discover_media_sources

    media_sources = [c for c in discover_media_sources(album_dir) if c.is_ios]

    if not media_sources:
        return FixIosResult()

    rc_result = None
    rj_result = None
    ru_result = None
    orphan_by_dir: list[tuple[str, tuple[str, ...]]] = []
    orphan_sidecar_by_dir: list[tuple[str, tuple[str, ...]]] = []
    higher_quality_by_dir: list[tuple[str, tuple[str, ...]]] = []
    miscat_result = None

    if refresh_combined_flag:
        total_heic = 0
        total_mov = 0
        total_jpeg_converted = 0
        total_jpeg_copied = 0
        total_jpeg_skipped = 0
        for ms in media_sources:
            result = refresh_combined(
                album_dir,
                ms,
                link_mode=link_mode,
                dry_run=dry_run,
                on_stage_start=on_refresh_combined_stage_start,
                on_stage_end=on_refresh_combined_stage_end,
            )
            total_heic += result.heic.copied
            total_mov += result.mov.copied
            total_jpeg_converted += result.jpeg.converted if result.jpeg else 0
            total_jpeg_copied += result.jpeg.copied if result.jpeg else 0
            total_jpeg_skipped += result.jpeg.skipped if result.jpeg else 0
        rc_result = FixIosRefreshCombinedResult(
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
        rj_result = FixIosRefreshJpegResult(
            converted=total_converted,
            copied=total_copied,
            skipped=total_skipped,
        )

    if rm_upstream:
        total_heic_jpeg = 0
        total_heic_combined = 0
        total_heic_rendered = 0
        total_heic_orig = 0
        total_mov_rendered = 0
        total_mov_orig = 0
        for ms in media_sources:
            result_rm = _do_rm_upstream(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd)
            total_heic_jpeg += len(result_rm.heic.removed_jpeg)
            total_heic_combined += len(result_rm.heic.removed_combined)
            total_heic_rendered += len(result_rm.heic.removed_rendered)
            total_heic_orig += len(result_rm.heic.removed_orig)
            total_mov_rendered += len(result_rm.mov.removed_rendered)
            total_mov_orig += len(result_rm.mov.removed_orig)
        ru_result = FixIosRmUpstreamResult(
            heic_jpeg=total_heic_jpeg,
            heic_combined=total_heic_combined,
            heic_rendered=total_heic_rendered,
            heic_orig=total_heic_orig,
            mov_rendered=total_mov_rendered,
            mov_orig=total_mov_orig,
        )

    if rm_orphan:
        for ms in media_sources:
            result_orphan = _do_rm_orphan(
                album_dir, ms, dry_run=dry_run, log_cwd=log_cwd
            )
            orphan_by_dir.extend(result_orphan.heic.removed_by_dir)
            orphan_by_dir.extend(result_orphan.mov.removed_by_dir)

    if rm_orphan_sidecar:
        for ms in media_sources:
            result_meta = _do_rm_orphan_sidecar(
                album_dir, ms, dry_run=dry_run, log_cwd=log_cwd
            )
            orphan_sidecar_by_dir.extend(result_meta.removed_by_dir)

    if prefer_higher_quality_when_dups:
        for ms in media_sources:
            result_hq = _do_prefer_higher_quality(
                album_dir, ms, dry_run=dry_run, log_cwd=log_cwd
            )
            higher_quality_by_dir.extend(result_hq.removed_by_dir)

    miscat_action = (
        "rm"
        if rm_miscategorized
        else "rm-safe"
        if rm_miscategorized_safe
        else "mv"
        if mv_miscategorized
        else None
    )
    if miscat_action:
        fix_fn = {
            "rm": _do_rm_miscategorized,
            "rm-safe": _do_rm_miscategorized_safe,
            "mv": _do_mv_miscategorized,
        }[miscat_action]
        total_heic_from_orig = 0
        total_heic_from_rendered = 0
        total_mov_from_orig = 0
        total_mov_from_rendered = 0
        for ms in media_sources:
            result_miscat = fix_fn(album_dir, ms, dry_run=dry_run, log_cwd=log_cwd)
            total_heic_from_orig += len(result_miscat.heic.fixed_from_orig)
            total_heic_from_rendered += len(result_miscat.heic.fixed_from_rendered)
            total_mov_from_orig += len(result_miscat.mov.fixed_from_orig)
            total_mov_from_rendered += len(result_miscat.mov.fixed_from_rendered)
        miscat_result = FixIosMiscategorizedResult(
            action=miscat_action,
            heic_from_orig=total_heic_from_orig,
            heic_from_rendered=total_heic_from_rendered,
            mov_from_orig=total_mov_from_orig,
            mov_from_rendered=total_mov_from_rendered,
        )

    return FixIosResult(
        refresh_combined_result=rc_result,
        refresh_jpeg_result=rj_result,
        rm_upstream_result=ru_result,
        rm_orphan_removed_by_dir=tuple(orphan_by_dir),
        rm_orphan_sidecar_removed_by_dir=tuple(orphan_sidecar_by_dir),
        prefer_higher_quality_removed_by_dir=tuple(higher_quality_by_dir),
        miscategorized_result=miscat_result,
    )
