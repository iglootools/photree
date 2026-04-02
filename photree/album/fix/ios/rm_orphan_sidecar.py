"""rm-orphan-sidecar iOS fix operation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....common.fs import delete_files, list_files
from ...store.protocol import (
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    SIDECAR_EXTENSIONS,
    MediaSource,
)


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _img_number(filename: str) -> str:
    return "".join(c for c in filename if c.isdigit())


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
