"""rm-orphan-sidecar iOS fix operation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....common.fs import delete_files, file_ext, list_files
from ...store.media_sources import ios_img_number, ios_is_media
from ...store.protocol import (
    IOS_SIDECAR_EXTENSIONS,
    MediaSource,
)


def _find_orphan_sidecars(directory: Path) -> list[str]:
    """Find AAE files whose image number has no matching media file."""
    files = list_files(directory)
    media_numbers = {ios_img_number(f) for f in files if ios_is_media(f)}
    return sorted(
        f
        for f in files
        if file_ext(f) in IOS_SIDECAR_EXTENSIONS
        and ios_img_number(f) not in media_numbers
    )


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
        delete_files(d, orphans, dry_run=dry_run)
        results.append((d.name, tuple(orphans)))

    return RmOrphanSidecarResult(removed_by_dir=tuple(results))
