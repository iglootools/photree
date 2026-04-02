"""Fix operations for iOS albums.

Each function orchestrates a specific fix: deleting stale data, rebuilding
from sources, and returning a structured result. CLI concerns (progress bars,
output formatting, exit codes) are handled by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..fs import (
    MediaSource,
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    PICTURE_PRIORITY_EXTENSIONS,
    SIDECAR_EXTENSIONS,
    delete_files,
    list_files,
    move_files,
)


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _img_number(filename: str) -> str:
    return "".join(c for c in filename if c.isdigit())


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

    any_fix = rm_orphan_sidecar or prefer_higher_quality_when_dups or miscat_flags > 0
    if not any_fix:
        raise FixIosValidationError(
            "No fix specified. Run photree album fix-ios --help for available fixes."
        )


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

    rm_orphan_sidecar_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()
    prefer_higher_quality_removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...] = ()
    miscategorized_result: FixIosMiscategorizedResult | None = None


# Aliases for use within run_fix_ios where parameter names shadow module functions
_do_rm_orphan_sidecar = rm_orphan_sidecar
_do_prefer_higher_quality = prefer_higher_quality_when_dups
_do_rm_miscategorized = rm_miscategorized
_do_rm_miscategorized_safe = rm_miscategorized_safe
_do_mv_miscategorized = mv_miscategorized


def run_fix_ios(
    album_dir: Path,
    *,
    dry_run: bool,
    log_cwd: Path | None = None,
    rm_orphan_sidecar: bool = False,
    prefer_higher_quality_when_dups: bool = False,
    rm_miscategorized: bool = False,
    rm_miscategorized_safe: bool = False,
    mv_miscategorized: bool = False,
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

    orphan_sidecar_by_dir: list[tuple[str, tuple[str, ...]]] = []
    higher_quality_by_dir: list[tuple[str, tuple[str, ...]]] = []
    miscat_result = None

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
        rm_orphan_sidecar_removed_by_dir=tuple(orphan_sidecar_by_dir),
        prefer_higher_quality_removed_by_dir=tuple(higher_quality_by_dir),
        miscategorized_result=miscat_result,
    )
