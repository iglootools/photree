"""
Import a std (non-iOS) media source from a ``to-import-std-<name>/`` dir.

The staging dir contains ``orig/`` and ``edit/`` subfolders whose files are
imported directly into the std archive (``orig-img``/``orig-vid`` and
``edit-img``/``edit-vid``), split by extension. Files are matched across
directories by filename stem. Unlike iOS, the files themselves are imported
(there is no Image Capture selection list). Validation refuses a staging dir
holding anything else, since nothing else would be imported; on success the
copied files are removed from the staging dir, and with them the dir itself.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from photree.album.check.std import (
    DuplicateStem,
    OrphanEdits,
    check_duplicate_stems,
    find_orphan_edits,
    folded_stem,
)
from photree.album.formats import IMG_EXTENSIONS, VID_EXTENSIONS
from photree.album.importer.archive_copy import copy_into_archive
from photree.album.importer.collision import ArchiveCollision
from photree.album.importer.staging_cleanup import remove_dir_if_only_hidden_files
from photree.album.importer.tasks import ImportTask
from photree.album.store.media_source import MediaSource
from photree.common.fs import file_ext, list_files

ORIG_SUBDIR = "orig"
EDIT_SUBDIR = "edit"

_MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS


@dataclass(frozen=True)
class StdNoMediaError:
    """The staging dir holds no media file under ``orig/`` or ``edit/``."""


@dataclass(frozen=True)
class StdUnsupportedEntries:
    """
    Staging entries the import would not copy, relative to the staging dir.

    Anything but an image or a video directly under ``orig/`` or ``edit/``:
    another file type, a subdirectory, or an entry beside ``orig/`` and
    ``edit/``. A directory ends with ``/``. Hidden entries (``.DS_Store``) are
    not listed.
    """

    entries: tuple[str, ...]


# Validation errors for a std task: an empty staging dir, entries the import
# would leave out, several files sharing a stem within ``orig/`` or ``edit/``,
# or edits with no original.
type StdValidationError = (
    StdNoMediaError | StdUnsupportedEntries | DuplicateStem | OrphanEdits
)


@dataclass(frozen=True)
class StdImportResult:
    """
    The outcome of importing one std media source.

    *imported* counts the media files copied.
    """

    media_source_name: str
    imported: int


def _is_media(filename: str) -> bool:
    return file_ext(filename) in _MEDIA_EXTENSIONS


def _is_hidden(path: Path) -> bool:
    return path.name.startswith(".")


def _entry_name(path: Path, staging: Path) -> str:
    """*path* relative to *staging*, with a trailing ``/`` for a directory."""
    name = path.relative_to(staging).as_posix()
    return f"{name}/" if path.is_dir() else name


class MissingStagingDirError(ValueError):
    """A std import task carries no ``to-import-std`` staging directory."""

    def __init__(self, task: str) -> None:
        """Build the error from the name of the task that lacks one."""
        self.task = task
        super().__init__(f"std import task '{task}' has no to-import-std staging dir")


def _staging_dir(task: ImportTask) -> Path:
    match task.staging_dir:
        case None:
            raise MissingStagingDirError(task.name)
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
    """
    Return whether the task's ``orig/`` or ``edit/`` holds a media file.

    Raises :class:`MissingStagingDirError` when *task* has no staging dir.
    """
    return bool(_staged_media(task))


def _visible_entries(directory: Path) -> list[Path]:
    """Non-hidden entries of *directory*; none when it is not a directory."""
    return (
        [p for p in directory.iterdir() if not _is_hidden(p)]
        if directory.is_dir()
        else []
    )


def _unsupported_entries(staging: Path) -> tuple[str, ...]:
    """Every visible staging entry the import would not copy; see the error."""
    subdirs = (ORIG_SUBDIR, EDIT_SUBDIR)
    beside_subdirs = [
        p for p in _visible_entries(staging) if not (p.is_dir() and p.name in subdirs)
    ]
    in_subdirs = [
        p
        for sub in subdirs
        for p in _visible_entries(staging / sub)
        if not (p.is_file() and _is_media(p.name))
    ]
    return tuple(
        sorted(_entry_name(p, staging) for p in [*beside_subdirs, *in_subdirs]),
    )


def _orphan_edits(staging: Path) -> tuple[str, ...]:
    """Staged edits with no original, images and videos matched apart."""
    return tuple(
        sorted(
            f
            for extensions in (IMG_EXTENSIONS, VID_EXTENSIONS)
            for f in find_orphan_edits(
                staging / ORIG_SUBDIR,
                staging / EDIT_SUBDIR,
                extensions,
            )
        ),
    )


def validate_std_task(task: ImportTask) -> tuple[StdValidationError, ...]:
    """
    Validate a std import task.

    Mirrors existing std media source rules (see
    :func:`photree.album.check.std.check_std_media_source_integrity`):
    requires at least one media file, rejects duplicate stems within
    ``orig/`` or ``edit/``, and rejects an ``edit/`` file with no ``orig/``
    file of the same stem and kind (image or video), which the browsable dir
    would leave out and ``album fix --rm-orphan`` would delete
    (:class:`~photree.album.check.std.OrphanEdits`).

    Also rejects a staging dir holding anything the import would not copy
    (:class:`StdUnsupportedEntries`): the import consumes the staging dir, so
    the user decides where those files go rather than finding them gone.
    """
    staging = _staging_dir(task)
    unsupported = _unsupported_entries(staging)
    orphans = _orphan_edits(staging)
    return (
        *(() if has_media(task) else (StdNoMediaError(),)),
        *((StdUnsupportedEntries(unsupported),) if unsupported else ()),
        *check_duplicate_stems(staging / ORIG_SUBDIR, _MEDIA_EXTENSIONS),
        *check_duplicate_stems(staging / EDIT_SUBDIR, _MEDIA_EXTENSIONS),
        *((OrphanEdits(EDIT_SUBDIR, orphans),) if orphans else ()),
    )


def _existing_archive_stems(album_dir: Path, ms: MediaSource) -> set[str]:
    return {
        folded_stem(f)
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
    """
    Find the staged filename stems that the target archive already holds.

    Matched by stem regardless of extension and of case (see
    :func:`~photree.album.check.std.folded_stem`), across the four archive
    dirs. The keys are the staged files' stems as they are written.
    """
    ms = task.media_source
    existing = _existing_archive_stems(album_dir, ms)
    collisions = sorted(
        {Path(f).stem for f in _staged_media(task) if folded_stem(f) in existing},
    )
    return ArchiveCollision(ms, tuple(collisions)) if collisions else None


def _archive_target(
    album_dir: Path,
    filename: str,
    img_dst: str,
    vid_dst: str,
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
    album_dir: Path,
    staging: Path,
    ms: MediaSource,
) -> list[tuple[Path, Path]]:
    """``(source file, archive dir)`` for every staged media file."""
    subdir_targets = (
        (ORIG_SUBDIR, ms.orig_img_dir, ms.orig_vid_dir),
        (EDIT_SUBDIR, ms.edit_img_dir, ms.edit_vid_dir),
    )
    return [
        (staging / src_sub / f, dst)
        for src_sub, img_dst, vid_dst in subdir_targets
        for f in list_files(staging / src_sub)
        if (dst := _archive_target(album_dir, f, img_dst, vid_dst)) is not None
    ]


def _consume_staging(staging: Path, copied: Sequence[Path]) -> None:
    """
    Remove the *copied* files, then each staging dir they leave empty.

    Never the whole tree: validation refuses a staging dir holding anything
    else, but should something appear in between, it stays where it is.
    """
    for src in copied:
        src.unlink()
    for directory in (staging / ORIG_SUBDIR, staging / EDIT_SUBDIR, staging):
        remove_dir_if_only_hidden_files(directory)


def import_std_source(
    album_dir: Path,
    task: ImportTask,
    *,
    dry_run: bool = False,
) -> StdImportResult:
    """
    Import one std media source from its staging directory.

    Splits each staging subfolder by extension into the archive's image/video
    directories, all or nothing
    (:func:`~photree.album.importer.archive_copy.copy_into_archive`), then (on
    a non-dry run) removes the copied files from the staging directory, and
    the directory once nothing else is left in it.

    The archive collision check (:func:`find_std_collision`) is the caller's
    job, before any mutation: :func:`photree.album.importer.album_import.run_import`
    runs it for every task up front.
    """
    staging = _staging_dir(task)
    copies = _plan_copies(album_dir, staging, task.media_source)

    if not dry_run:
        copy_into_archive(album_dir, copies)
        _consume_staging(staging, [src for src, _ in copies])

    return StdImportResult(
        media_source_name=task.media_source.name,
        imported=len(copies),
    )
