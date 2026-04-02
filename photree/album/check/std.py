"""Std (non-iOS) media source integrity checks.

Validates browsable directory consistency, JPEG completeness, and
duplicate filename stems for std media sources with archives.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...common.fs import file_ext, list_files
from ..store.protocol import IMG_EXTENSIONS, VID_EXTENSIONS, MediaSource
from .browsable import BrowsableDirCheck, check_browsable_dir
from .jpeg import JpegCheck, check_jpeg_dir


def check_duplicate_stems(
    directory: Path, media_extensions: frozenset[str]
) -> tuple[str, ...]:
    """Check for files with the same stem but different extensions.

    E.g. ``photo1.heic`` + ``photo1.jpg`` in the same directory.
    """
    stems: dict[str, list[str]] = {}
    for f in list_files(directory):
        if file_ext(f) in media_extensions:
            stems.setdefault(Path(f).stem, []).append(f)

    return tuple(
        f"{directory.name}/: stem {stem} has multiple media files: {', '.join(candidates)}"
        for stem, candidates in sorted(stems.items())
        if len(candidates) > 1
    )


@dataclass(frozen=True)
class StdMediaSourceIntegrityResult:
    """Integrity check result for a single std media source."""

    browsable_img: BrowsableDirCheck
    browsable_vid: BrowsableDirCheck
    browsable_jpg: JpegCheck
    duplicate_stems: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return (
            self.browsable_img.success
            and self.browsable_vid.success
            and self.browsable_jpg.success
            and not self.duplicate_stems
        )


def check_std_media_source_integrity(
    album_dir: Path,
    ms: MediaSource,
    *,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> StdMediaSourceIntegrityResult:
    """Run integrity checks for a single std media source.

    Only runs on std media sources that have an archive directory
    (``std-{name}/``) on disk.
    """
    assert ms.is_std, "std integrity checks require a std media source"

    browsable_img = check_browsable_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        media_extensions=IMG_EXTENSIONS,
        key_fn=ms.key_fn,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )

    browsable_vid = check_browsable_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        album_dir / ms.vid_dir,
        media_extensions=VID_EXTENSIONS,
        key_fn=ms.key_fn,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )

    browsable_jpg = check_jpeg_dir(
        album_dir / ms.img_dir,
        album_dir / ms.jpg_dir,
    )

    all_media = IMG_EXTENSIONS | VID_EXTENSIONS
    duplicate_stems = tuple(
        w
        for subdir_name in ms.all_subdirs
        if (album_dir / subdir_name).is_dir()
        for w in check_duplicate_stems(album_dir / subdir_name, all_media)
    )

    return StdMediaSourceIntegrityResult(
        browsable_img=browsable_img,
        browsable_vid=browsable_vid,
        browsable_jpg=browsable_jpg,
        duplicate_stems=duplicate_stems,
    )
