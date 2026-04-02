"""prefer-higher-quality-when-dups iOS fix operation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ....fs import (
    MediaSource,
    IOS_IMG_EXTENSIONS,
    PICTURE_PRIORITY_EXTENSIONS,
    delete_files,
    list_files,
)


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _img_number(filename: str) -> str:
    return "".join(c for c in filename if c.isdigit())


def _find_non_heic_dups_in_dir(
    directory: Path, media_extensions: frozenset[str]
) -> list[str]:
    """Find non-HEIC media files that share an image number with a HEIC file."""
    files = list_files(directory)
    media_by_number: dict[str, list[str]] = {}
    for f in files:
        if _ext(f) in media_extensions:
            media_by_number.setdefault(_img_number(f), []).append(f)

    return sorted(
        non_heic
        for candidates in media_by_number.values()
        if any(_ext(f) in PICTURE_PRIORITY_EXTENSIONS for f in candidates)
        for non_heic in candidates
        if _ext(non_heic) not in PICTURE_PRIORITY_EXTENSIONS
    )


@dataclass(frozen=True)
class PreferHigherQualityResult:
    """Result of removing non-HEIC duplicates."""

    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def total(self) -> int:
        return sum(len(files) for _, files in self.removed_by_dir)


def prefer_higher_quality_when_dups(
    album_dir: Path,
    ms: MediaSource,
    *,
    dry_run: bool = False,
) -> PreferHigherQualityResult:
    """Delete lower-quality duplicates when multiple formats exist for the same number.

    Scans all image subdirectories. For each image number that has multiple
    format variants, keeps the highest-quality file (DNG > HEIC > JPG/PNG)
    and deletes the rest.
    """
    assert ms.is_ios, "ios_fixes operations require an iOS media source"
    directories = (
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        album_dir / ms.jpg_dir,
    )

    def _process_dir(d: Path) -> tuple[str, tuple[str, ...]] | None:
        if not d.is_dir():
            return None
        dups = _find_non_heic_dups_in_dir(d, IOS_IMG_EXTENSIONS)
        if not dups:
            return None
        delete_files(d, dups, dry_run=dry_run)
        return (d.name, tuple(dups))

    return PreferHigherQualityResult(
        removed_by_dir=tuple(
            result for d in directories if (result := _process_dir(d)) is not None
        )
    )
