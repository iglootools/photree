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
from ..check.std import check_duplicate_stems
from ..store.protocol import IMG_EXTENSIONS, VID_EXTENSIONS

if TYPE_CHECKING:
    from .tasks import ImportTask

ORIG_SUBDIR = "orig"
EDIT_SUBDIR = "edit"

_MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS


@dataclass(frozen=True)
class StdImportResult:
    """Result of importing a single std media source."""

    media_source_name: str
    imported: int
    skipped_non_media: tuple[str, ...]


def _is_media(filename: str) -> bool:
    return file_ext(filename) in _MEDIA_EXTENSIONS


def has_media(task: ImportTask) -> bool:
    """Return True if the std task's staging dir has at least one media file."""
    staging = task.staging_dir
    assert staging is not None, "std task requires a staging dir"
    return any(
        _is_media(f)
        for sub in (ORIG_SUBDIR, EDIT_SUBDIR)
        for f in list_files(staging / sub)
    )


def validate_std_task(task: ImportTask) -> list[str]:
    """Validate a std import task. Returns a list of error messages.

    Mirrors existing std media source rules (see
    :func:`photree.album.check.std.check_std_media_source_integrity`):
    requires at least one media file, and rejects duplicate stems within
    ``orig/`` or ``edit/``. An ``edit/`` file with no matching ``orig/`` stem
    is allowed (same as existing std sources) — it is imported but omitted from
    the browsable dir.
    """
    staging = task.staging_dir
    assert staging is not None, "std task requires a staging dir"
    orig = staging / ORIG_SUBDIR
    edit = staging / EDIT_SUBDIR

    orig_media = [f for f in list_files(orig) if _is_media(f)]
    edit_media = [f for f in list_files(edit) if _is_media(f)]

    errors: list[str] = []
    if not orig_media and not edit_media:
        errors.append(f"no media files found in {ORIG_SUBDIR}/ or {EDIT_SUBDIR}/")
    errors.extend(check_duplicate_stems(orig, _MEDIA_EXTENSIONS))
    errors.extend(check_duplicate_stems(edit, _MEDIA_EXTENSIONS))
    return errors


def _existing_archive_stems(album_dir: Path, ms) -> set[str]:
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


def import_std_source(
    album_dir: Path,
    task: ImportTask,
    *,
    dry_run: bool = False,
) -> StdImportResult:
    """Import a std source's ``orig``/``edit`` files into its archive.

    Splits each staging subfolder by extension into the archive's image/video
    directories, then (on a non-dry run) removes the staging directory.
    """
    ms = task.media_source
    staging = task.staging_dir
    assert staging is not None, "std task requires a staging dir"

    # ── Pre-copy collision check (by filename stem) ──
    existing_stems = _existing_archive_stems(album_dir, ms)
    incoming_stems = {
        Path(f).stem
        for sub in (ORIG_SUBDIR, EDIT_SUBDIR)
        for f in list_files(staging / sub)
        if _is_media(f)
    }
    collisions = sorted(incoming_stems & existing_stems)
    if collisions:
        raise ValueError(
            f"Import would conflict with {len(collisions)} existing "
            f"file(s) in media source '{ms.name}':\n"
            + "".join(f"  {stem}\n" for stem in collisions[:10])
            + (
                f"  ... and {len(collisions) - 10} more\n"
                if len(collisions) > 10
                else ""
            )
            + f"Import into a different media source by renaming the staging "
            f"directory (current: to-import-std-{ms.name})."
        )

    # ── Copy files, splitting by extension ──
    subdir_targets = (
        (ORIG_SUBDIR, ms.orig_img_dir, ms.orig_vid_dir),
        (EDIT_SUBDIR, ms.edit_img_dir, ms.edit_vid_dir),
    )
    imported = 0
    skipped: list[str] = []
    for src_sub, img_dst, vid_dst in subdir_targets:
        src = staging / src_sub
        for f in list_files(src):
            ext = file_ext(f)
            if ext in IMG_EXTENSIONS:
                dst = album_dir / img_dst
            elif ext in VID_EXTENSIONS:
                dst = album_dir / vid_dst
            else:
                skipped.append(f"{src_sub}/{f}")
                continue
            if not dry_run:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy(src / f, dst / f)
            imported += 1

    # ── Consume the staging directory on success ──
    if not dry_run:
        shutil.rmtree(staging)

    return StdImportResult(
        media_source_name=ms.name,
        imported=imported,
        skipped_non_media=tuple(skipped),
    )
