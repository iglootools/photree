"""Miscategorized files iOS fix operations (rm / mv)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....fs import (
    MediaSource,
    delete_files,
    list_files,
    move_files,
)


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

    Returns (edited_in_orig, orig_in_edit) -- files that are in the wrong dir.
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
        delete_files(orig_dir, edited_in_orig, dry_run=dry_run)
        delete_files(edit_dir, orig_in_edit, dry_run=dry_run)
    elif action == "mv":
        move_files(orig_dir, edit_dir, edited_in_orig, dry_run=dry_run)
        move_files(edit_dir, orig_dir, orig_in_edit, dry_run=dry_run)

    return MiscategorizedDirResult(
        fixed_from_orig=tuple(edited_in_orig),
        fixed_from_rendered=tuple(orig_in_edit),
    )


def rm_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Delete files that are in the wrong directory (edited in orig or vice versa)."""
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    return MiscategorizedResult(
        heic=_fix_miscategorized_pair(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            action="rm",
            dry_run=dry_run,
        ),
        mov=_fix_miscategorized_pair(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            action="rm",
            dry_run=dry_run,
        ),
    )


def rm_miscategorized_safe(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Delete miscategorized files only if they already exist in the correct directory."""
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    return MiscategorizedResult(
        heic=_fix_miscategorized_pair(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            action="rm-safe",
            dry_run=dry_run,
        ),
        mov=_fix_miscategorized_pair(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            action="rm-safe",
            dry_run=dry_run,
        ),
    )


def mv_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Move files that are in the wrong directory to the correct one."""
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    return MiscategorizedResult(
        heic=_fix_miscategorized_pair(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            action="mv",
            dry_run=dry_run,
        ),
        mov=_fix_miscategorized_pair(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            action="mv",
            dry_run=dry_run,
        ),
    )
