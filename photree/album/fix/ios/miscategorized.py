"""Miscategorized files iOS fix operations (rm / mv)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ....common.fs import delete_files, list_files, move_files
from ...store.media_sources import ios_file_prefix
from ...store.protocol import MediaSource
from ..helpers import require_ios


class MiscategorizedAction(StrEnum):
    """What to do with a file found in the wrong archive directory."""

    RM = "rm"  # delete it
    RM_SAFE = "rm-safe"  # delete it only if it already exists in the right dir
    MV = "mv"  # move it to the right dir


class MiscategorizedMoveConflictError(FileExistsError):
    """Moving miscategorized files would overwrite files in the target dir.

    Raised before anything is moved. ``conflicts`` are filenames present in
    both directories; ``--rm-miscategorized-safe`` removes such duplicates.
    """

    def __init__(self, target_dir: str, conflicts: tuple[str, ...]) -> None:
        self.target_dir = target_dir
        self.conflicts = conflicts
        super().__init__(
            f"Moving into {target_dir} would overwrite {len(conflicts)} "
            f"existing file(s): {', '.join(conflicts)}"
        )


def _find_miscategorized(
    orig_dir: Path,
    edit_dir: Path,
) -> tuple[list[str], list[str]]:
    """Find miscategorized files.

    Returns (edited_in_orig, orig_in_edit) -- files that are in the wrong dir.
    Edited files are those with IMG_E or IMG_O prefix.
    Original files are those without E/O prefix.
    """
    orig_files = list_files(orig_dir)
    edit_files = list_files(edit_dir)

    edited_in_orig = sorted(f for f in orig_files if ios_file_prefix(f) in ("E", "O"))
    orig_in_edit = sorted(f for f in edit_files if ios_file_prefix(f) == "")

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


def _require_no_overwrite(files: list[str], target_dir: Path) -> None:
    """Refuse a move that would silently replace files in *target_dir*."""
    conflicts = tuple(_filter_safe(files, target_dir))
    if conflicts:
        raise MiscategorizedMoveConflictError(target_dir.name, conflicts)


def _fix_miscategorized_pair(
    orig_dir: Path,
    edit_dir: Path,
    *,
    action: MiscategorizedAction,
    dry_run: bool,
) -> MiscategorizedDirResult:
    """Fix miscategorized files for one orig/edit pair."""
    edited_in_orig, orig_in_edit = _find_miscategorized(orig_dir, edit_dir)

    match action:
        case MiscategorizedAction.RM:
            delete_files(orig_dir, edited_in_orig, dry_run=dry_run)
            delete_files(edit_dir, orig_in_edit, dry_run=dry_run)
        case MiscategorizedAction.RM_SAFE:
            edited_in_orig = _filter_safe(edited_in_orig, edit_dir)
            orig_in_edit = _filter_safe(orig_in_edit, orig_dir)
            delete_files(orig_dir, edited_in_orig, dry_run=dry_run)
            delete_files(edit_dir, orig_in_edit, dry_run=dry_run)
        case MiscategorizedAction.MV:
            # Check both directions before moving either, so a refusal
            # leaves the pair untouched.
            _require_no_overwrite(edited_in_orig, edit_dir)
            _require_no_overwrite(orig_in_edit, orig_dir)
            move_files(orig_dir, edit_dir, edited_in_orig, dry_run=dry_run)
            move_files(edit_dir, orig_dir, orig_in_edit, dry_run=dry_run)

    return MiscategorizedDirResult(
        fixed_from_orig=tuple(edited_in_orig),
        fixed_from_rendered=tuple(orig_in_edit),
    )


def fix_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    action: MiscategorizedAction,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Apply *action* to files in the wrong directory, for images and videos.

    Raises :class:`~..helpers.NotAnIosMediaSourceError` for std sources, and
    :class:`MiscategorizedMoveConflictError` when a move would overwrite.
    """
    require_ios(ms)
    return MiscategorizedResult(
        heic=_fix_miscategorized_pair(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            action=action,
            dry_run=dry_run,
        ),
        mov=_fix_miscategorized_pair(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            action=action,
            dry_run=dry_run,
        ),
    )


def rm_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Delete files that are in the wrong directory (edited in orig or vice versa)."""
    return fix_miscategorized(
        album_dir, ms, action=MiscategorizedAction.RM, dry_run=dry_run
    )


def rm_miscategorized_safe(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Delete miscategorized files only if they already exist in the correct directory."""
    return fix_miscategorized(
        album_dir, ms, action=MiscategorizedAction.RM_SAFE, dry_run=dry_run
    )


def mv_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Move files that are in the wrong directory to the correct one."""
    return fix_miscategorized(
        album_dir, ms, action=MiscategorizedAction.MV, dry_run=dry_run
    )
