"""
Copy an import task's files into the archive, all or nothing.

A copy that stops part-way (a full disk, Ctrl-C) must not leave some of the
task's files in the archive: the retry would find them, refuse the import as
a collision, and suggest the wrong recovery. So every file is copied into a
directory under ``.photree/`` first, on the album's filesystem, then renamed
into place, which is quick and does not fail for want of space.
"""

import shutil
from collections.abc import Sequence
from pathlib import Path

from photree.foundation.layout import PHOTREE_DIR

IMPORT_IN_PROGRESS_DIR = "import-in-progress"


def _in_progress_dir(album_dir: Path) -> Path:
    return album_dir / PHOTREE_DIR / IMPORT_IN_PROGRESS_DIR


def _copy_to_in_progress(
    album_dir: Path,
    src: Path,
    dst_dir: Path,
) -> tuple[Path, Path]:
    """Copy *src* beside its peers in the in-progress dir; return (copy, final)."""
    tmp_dir = _in_progress_dir(album_dir) / dst_dir.relative_to(album_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy(src, tmp_dir / src.name)), dst_dir / src.name


def _move_into_place(staged: Sequence[tuple[Path, Path]]) -> None:
    """
    Rename every copy to its final path; on failure, remove those already moved.

    A copy no longer in the in-progress dir is one this call moved: the
    caller's collision check guarantees no final path existed before.
    """
    try:
        for tmp, final in staged:
            final.parent.mkdir(parents=True, exist_ok=True)
            tmp.rename(final)
    except BaseException:
        for tmp, final in staged:
            if not tmp.exists():
                final.unlink(missing_ok=True)
        raise


def copy_into_archive(album_dir: Path, copies: Sequence[tuple[Path, Path]]) -> None:
    """
    Copy each ``(source file, archive dir)`` of *copies*, all or nothing.

    The archive dirs must lie under *album_dir*, and must not hold any of the
    files yet (the importers' collision checks). Leaves the archive as it was
    when any copy fails, and removes what a run killed outright left in the
    in-progress dir the next time it is called.
    """
    in_progress = _in_progress_dir(album_dir)
    shutil.rmtree(in_progress, ignore_errors=True)
    try:
        _move_into_place(
            [
                _copy_to_in_progress(album_dir, src, dst)
                # A pair listed twice would find its copy already moved.
                for src, dst in dict.fromkeys(copies)
            ],
        )
    finally:
        shutil.rmtree(in_progress, ignore_errors=True)
