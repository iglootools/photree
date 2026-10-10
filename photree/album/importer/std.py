"""Import a std (non-iOS) media source from a ``to-import-std-<name>/`` dir.

The staging dir contains ``orig/`` and ``edit/`` subfolders whose files are
imported directly into the std archive (``orig-img``/``orig-vid`` and
``edit-img``/``edit-vid``), split by extension. Files are matched across
directories by filename stem. Unlike iOS, the files themselves are imported
(there is no Image Capture selection list). On success the staging dir is
consumed (removed).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ...common.fs import file_ext, list_files
from ..check.std import DuplicateStem, check_duplicate_stems
from ..formats import IMG_EXTENSIONS, VID_EXTENSIONS
from ..store.media_source import MediaSource
from .collision import ArchiveCollision

if TYPE_CHECKING:
    from .tasks import ImportTask

ORIG_SUBDIR = "orig"
EDIT_SUBDIR = "edit"

_MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS


@dataclass(frozen=True)
class StdNoMediaError:
    """The staging dir holds no media file under ``orig/`` or ``edit/``."""


# Validation errors for a std task: an empty staging dir, or several files
# sharing a stem within ``orig/`` or ``edit/``.
StdValidationError = StdNoMediaError | DuplicateStem


@dataclass(frozen=True)
class StdImportResult:
    """Result of importing a single std media source."""

    media_source_name: str
    imported: int
    skipped_non_media: tuple[str, ...]


def _is_media(filename: str) -> bool:
    return file_ext(filename) in _MEDIA_EXTENSIONS


def _staging_dir(task: ImportTask) -> Path:
    match task.staging_dir:
        case None:
            raise ValueError(
                f"std import task '{task.name}' has no to-import-std staging dir"
            )
        case staging:
            return staging


def _staged_media(task: ImportTask) -> list[str]:
    """Media filenames in the staging dir's ``orig/`` and ``edit/`` subfolders."""
    staging = _staging_dir(task)
    return [
        f
        for sub in (ORIG_SUBDIR, EDIT_SUBDIR)
        for f in list_files(staging / sub)
        if _is_media(f)
    ]


def has_media(task: ImportTask) -> bool:
    """Return True if the std task's staging dir has at least one media file."""
    return bool(_staged_media(task))


def validate_std_task(task: ImportTask) -> tuple[StdValidationError, ...]:
    """Validate a std import task.

    Mirrors existing std media source rules (see
    :func:`photree.album.check.std.check_std_media_source_integrity`):
    requires at least one media file, and rejects duplicate stems within
    ``orig/`` or ``edit/``. An ``edit/`` file with no matching ``orig/`` stem
    is allowed (same as existing std sources) — it is imported but omitted from
    the browsable dir.
    """
    staging = _staging_dir(task)
    return (
        *(() if has_media(task) else (StdNoMediaError(),)),
        *check_duplicate_stems(staging / ORIG_SUBDIR, _MEDIA_EXTENSIONS),
        *check_duplicate_stems(staging / EDIT_SUBDIR, _MEDIA_EXTENSIONS),
    )


def _existing_archive_stems(album_dir: Path, ms: MediaSource) -> set[str]:
    """Collect stems already present in a std source's archive directories."""
    return {
        Path(f).stem
        for subdir in (
            ms.orig_img_dir,
            ms.orig_vid_dir,
            ms.edit_img_dir,
            ms.edit_vid_dir,
        )
        for f in list_files(album_dir / subdir)
        if _is_media(f)
    }


def find_std_collision(album_dir: Path, task: ImportTask) -> ArchiveCollision | None:
    """Return the staged stems already present in the task's std archive."""
    ms = task.media_source
    incoming = {Path(f).stem for f in _staged_media(task)}
    collisions = sorted(incoming & _existing_archive_stems(album_dir, ms))
    return ArchiveCollision(ms, tuple(collisions)) if collisions else None


def _archive_target(
    album_dir: Path, filename: str, img_dst: str, vid_dst: str
) -> Path | None:
    """Archive dir a staged file goes to, or None when it is not media."""
    match file_ext(filename):
        case ext if ext in IMG_EXTENSIONS:
            return album_dir / img_dst
        case ext if ext in VID_EXTENSIONS:
            return album_dir / vid_dst
        case _:
            return None


def _plan_copies(
    album_dir: Path, staging: Path, ms: MediaSource
) -> list[tuple[str, Path, Path | None]]:
    """``(display name, source file, archive dir or None)`` for every staged file."""
    subdir_targets = (
        (ORIG_SUBDIR, ms.orig_img_dir, ms.orig_vid_dir),
        (EDIT_SUBDIR, ms.edit_img_dir, ms.edit_vid_dir),
    )
    return [
        (
            f"{src_sub}/{f}",
            staging / src_sub / f,
            _archive_target(album_dir, f, img_dst, vid_dst),
        )
        for src_sub, img_dst, vid_dst in subdir_targets
        for f in list_files(staging / src_sub)
    ]


def import_std_source(
    album_dir: Path,
    task: ImportTask,
    *,
    dry_run: bool = False,
) -> StdImportResult:
    """Import a std source's ``orig``/``edit`` files into its archive.

    Splits each staging subfolder by extension into the archive's image/video
    directories, then (on a non-dry run) removes the staging directory.

    The archive collision check (:func:`find_std_collision`) is the caller's
    job, before any mutation: :func:`photree.album.importer.album_import.run_import`
    runs it for every task up front.
    """
    staging = _staging_dir(task)
    copies = _plan_copies(album_dir, staging, task.media_source)
    media = [(src, dst) for _, src, dst in copies if dst is not None]

    if not dry_run:
        for src, dst in media:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst / src.name)
        # Consume the staging directory on success
        shutil.rmtree(staging)

    return StdImportResult(
        media_source_name=task.media_source.name,
        imported=len(media),
        skipped_non_media=tuple(name for name, _, dst in copies if dst is None),
    )
