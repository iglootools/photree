"""The fix for iOS files in the wrong archive directory (orig vs edit)."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.fix.helpers import require_ios
from photree.album.store.file_matching import ios_file_prefix
from photree.album.store.media_source import MediaSource
from photree.common.fs import delete_files, list_files, move_files


class MiscategorizedAction(StrEnum):
    """What to do with a file found in the wrong archive directory."""

    RM = "rm"  # delete it
    RM_SAFE = "rm-safe"  # delete it only if it already exists in the right dir
    MV = "mv"  # move it to the right dir


class MiscategorizedMoveConflictError(FileExistsError):
    """
    Moving miscategorized files would overwrite files in the target dir.

    Raised before anything is moved. ``target_dir`` is album-relative (e.g.
    ``ios-main/edit-img``); ``conflicts`` are filenames present in both
    directories, which ``--rm-miscategorized-safe`` removes.
    """

    def __init__(self, target_dir: str, conflicts: tuple[str, ...]) -> None:
        """Build the error from the album-relative target dir and the clashing files."""
        self.target_dir = target_dir
        self.conflicts = conflicts
        super().__init__(
            f"Moving into {target_dir} would overwrite {len(conflicts)} "
            f"existing file(s): {', '.join(conflicts)}",
        )


def _find_miscategorized(
    orig_dir: Path,
    edit_dir: Path,
) -> tuple[list[str], list[str]]:
    """
    Return ``(edited_in_orig, orig_in_edit)``: the files that are in the wrong dir.

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
    """
    The files fixed in one orig/edit directory pair.

    *fixed_from_orig* holds the edited files found in the orig directory,
    *fixed_from_rendered* the original files found in the edit directory.
    """

    fixed_from_orig: tuple[str, ...]
    fixed_from_rendered: tuple[str, ...]


@dataclass(frozen=True)
class MiscategorizedResult:
    """The miscategorized files fixed in a media source, for images and videos."""

    heic: MiscategorizedDirResult
    mov: MiscategorizedDirResult

    @property
    def total(self) -> int:
        """Return the number of files fixed across both pairs."""
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


@dataclass(frozen=True)
class _PairPlan:
    """The files to fix in one orig/edit directory pair, computed without moving."""

    orig_dir: Path
    edit_dir: Path
    from_orig: tuple[str, ...]
    from_edit: tuple[str, ...]

    def move_conflicts(self) -> list[tuple[Path, tuple[str, ...]]]:
        """Return each target directory a move would overwrite files in, with them."""
        return [
            (target, conflicts)
            for files, target in (
                (self.from_orig, self.edit_dir),
                (self.from_edit, self.orig_dir),
            )
            if (conflicts := tuple(_filter_safe(list(files), target)))
        ]

    def apply(self, action: MiscategorizedAction, *, dry_run: bool) -> None:
        """Delete or move the planned files, as *action* says."""
        match action:
            case MiscategorizedAction.RM | MiscategorizedAction.RM_SAFE:
                delete_files(self.orig_dir, list(self.from_orig), dry_run=dry_run)
                delete_files(self.edit_dir, list(self.from_edit), dry_run=dry_run)
            case MiscategorizedAction.MV:
                move_files(
                    self.orig_dir,
                    self.edit_dir,
                    list(self.from_orig),
                    dry_run=dry_run,
                )
                move_files(
                    self.edit_dir,
                    self.orig_dir,
                    list(self.from_edit),
                    dry_run=dry_run,
                )

    def result(self) -> MiscategorizedDirResult:
        """Return the files this pair's fix acts on."""
        return MiscategorizedDirResult(
            fixed_from_orig=self.from_orig,
            fixed_from_rendered=self.from_edit,
        )


def _plan_pair(
    orig_dir: Path,
    edit_dir: Path,
    action: MiscategorizedAction,
) -> _PairPlan:
    edited_in_orig, orig_in_edit = _find_miscategorized(orig_dir, edit_dir)
    safe = action == MiscategorizedAction.RM_SAFE
    return _PairPlan(
        orig_dir=orig_dir,
        edit_dir=edit_dir,
        from_orig=tuple(
            _filter_safe(edited_in_orig, edit_dir) if safe else edited_in_orig,
        ),
        from_edit=tuple(
            _filter_safe(orig_in_edit, orig_dir) if safe else orig_in_edit,
        ),
    )


@dataclass(frozen=True)
class MiscategorizedPlan:
    """The miscategorized files of one media source, and the action to take."""

    album_dir: Path
    action: MiscategorizedAction
    heic: _PairPlan
    mov: _PairPlan

    def move_conflict(self) -> MiscategorizedMoveConflictError | None:
        """Return the error a move would raise for overwriting files, if any."""
        conflicts = (
            [*self.heic.move_conflicts(), *self.mov.move_conflicts()]
            if self.action == MiscategorizedAction.MV
            else []
        )
        return (
            MiscategorizedMoveConflictError(
                conflicts[0][0].relative_to(self.album_dir).as_posix(),
                conflicts[0][1],
            )
            if conflicts
            else None
        )


def plan_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    action: MiscategorizedAction,
) -> MiscategorizedPlan:
    """
    Find the files of *ms* in the wrong archive directory, without touching them.

    Raises :class:`~photree.album.fix.helpers.NotAnIosMediaSourceError` for std
    sources.
    """
    require_ios(ms)
    return MiscategorizedPlan(
        album_dir=album_dir,
        action=action,
        heic=_plan_pair(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            action,
        ),
        mov=_plan_pair(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            action,
        ),
    )


def check_miscategorized_plans(plans: list[MiscategorizedPlan]) -> None:
    """Raise the first :class:`MiscategorizedMoveConflictError` among *plans*."""
    conflict = next(
        (err for plan in plans if (err := plan.move_conflict()) is not None),
        None,
    )
    if conflict is not None:
        raise conflict


def apply_miscategorized(
    plan: MiscategorizedPlan,
    *,
    dry_run: bool,
) -> MiscategorizedResult:
    """
    Delete or move the planned files.

    Does not check for move conflicts: run :func:`check_miscategorized_plans`
    on every plan first, so a conflict leaves all of them untouched.
    """
    plan.heic.apply(plan.action, dry_run=dry_run)
    plan.mov.apply(plan.action, dry_run=dry_run)
    return MiscategorizedResult(heic=plan.heic.result(), mov=plan.mov.result())


def fix_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    action: MiscategorizedAction,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """
    Delete or move the files that sit in the wrong archive directory.

    Raises :class:`~photree.album.fix.helpers.NotAnIosMediaSourceError` for std
    sources, and :class:`MiscategorizedMoveConflictError`, before touching any
    file, when a move would overwrite one.
    """
    plan = plan_miscategorized(album_dir, ms, action=action)
    check_miscategorized_plans([plan])
    return apply_miscategorized(plan, dry_run=dry_run)


def rm_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Delete files that are in the wrong directory (edited in orig or vice versa)."""
    return fix_miscategorized(
        album_dir,
        ms,
        action=MiscategorizedAction.RM,
        dry_run=dry_run,
    )


def rm_miscategorized_safe(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """Delete miscategorized files only where the correct directory has them already."""
    return fix_miscategorized(
        album_dir,
        ms,
        action=MiscategorizedAction.RM_SAFE,
        dry_run=dry_run,
    )


def mv_miscategorized(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> MiscategorizedResult:
    """
    Move files that sit in the wrong archive directory to the right one.

    Raises :class:`~photree.album.fix.helpers.NotAnIosMediaSourceError` for
    std sources, and :class:`MiscategorizedMoveConflictError`, before moving
    anything, when a move would overwrite a file.
    """
    return fix_miscategorized(
        album_dir,
        ms,
        action=MiscategorizedAction.MV,
        dry_run=dry_run,
    )
