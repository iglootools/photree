"""The fix that keeps only the best format of each iOS image number."""

from pathlib import Path

from photree.album.fix.helpers import require_ios
from photree.album.fix.removed_files import RemovedFiles
from photree.album.formats import IOS_IMG_EXTENSIONS, PICTURE_PRIORITY_EXTENSIONS
from photree.album.store.file_matching import group_by_key, pick_media_priority
from photree.album.store.media_source import MediaSource, ios_img_number
from photree.common.fs import delete_files, file_ext, list_files


def _find_lower_quality_dups_in_dir(
    directory: Path,
    media_extensions: frozenset[str],
) -> list[str]:
    """
    Find files outranked by another format of the same image number.

    Only numbers with at least one priority format (DNG, HEIC) are
    touched: between equal-rank formats (JPG vs PNG) there is no
    higher-quality file to prefer. Within such a group, everything but the
    single best file (:func:`pick_media_priority`) is returned — including a
    HEIC that sits next to a DNG.
    """
    groups = group_by_key(list_files(directory), media_extensions, ios_img_number)
    return sorted(
        f
        for candidates in groups.values()
        if len(candidates) > 1
        and any(file_ext(c) in PICTURE_PRIORITY_EXTENSIONS for c in candidates)
        for f in candidates
        if f != pick_media_priority(candidates)
    )


def _remove_dups_in_dir(directory: Path, *, dry_run: bool) -> tuple[str, ...]:
    dups = _find_lower_quality_dups_in_dir(directory, IOS_IMG_EXTENSIONS)
    delete_files(directory, dups, dry_run=dry_run)
    return tuple(dups)


def prefer_higher_quality_when_dups(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> RemovedFiles:
    """
    Keep the highest-quality variant of each image number and delete the rest.

    Scans all image subdirectories. For each image number that has multiple
    format variants, keeps the single highest-quality file (DNG > HEIC > others).
    """
    require_ios(ms)
    directories = (
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        album_dir / ms.jpg_dir,
    )
    return RemovedFiles(
        removed_by_dir=tuple(
            (d.name, removed)
            for d in directories
            if d.is_dir() and (removed := _remove_dups_in_dir(d, dry_run=dry_run))
        ),
    )
