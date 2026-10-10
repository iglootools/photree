"""Std (non-iOS) media source integrity checks.

Validates browsable directory consistency, JPEG completeness, and
duplicate filename stems for std media sources with archives.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import TypedDict

from ...common.fs import file_ext, list_files
from ...fsprotocol import LinkMode
from ..formats import IMG_EXTENSIONS, VID_EXTENSIONS
from ..store.media_source import MediaSource
from .browsable import BrowsableDirCheck, check_browsable_dir
from .jpeg import JpegCheck, check_jpeg_dir


@dataclass(frozen=True)
class DuplicateStem:
    """Several media files in *directory* share *stem* (e.g. ``a.heic`` + ``a.jpg``).

    *directory* is the directory's name relative to its parent (``orig``,
    ``orig-img``, ...), which is how the formatters display it.
    """

    directory: str
    stem: str
    files: tuple[str, ...]


def _stem(filename: str) -> str:
    return Path(filename).stem


def check_duplicate_stems(
    directory: Path, media_extensions: frozenset[str]
) -> tuple[DuplicateStem, ...]:
    """Check for files with the same stem but different extensions.

    E.g. ``photo1.heic`` + ``photo1.jpg`` in the same directory.
    """
    media = sorted(
        (f for f in list_files(directory) if file_ext(f) in media_extensions),
        key=_stem,
    )
    return tuple(
        DuplicateStem(directory=directory.name, stem=key, files=files)
        for key, group in groupby(media, key=_stem)
        if len(files := tuple(group)) > 1
    )


@dataclass(frozen=True)
class StdMediaSourceIntegrityResult:
    """Integrity check result for a single std media source."""

    browsable_img: BrowsableDirCheck
    browsable_vid: BrowsableDirCheck
    browsable_jpg: JpegCheck
    duplicate_stems: tuple[DuplicateStem, ...] = ()

    @property
    def success(self) -> bool:
        return (
            self.browsable_img.success
            and self.browsable_vid.success
            and self.browsable_jpg.success
            and not self.duplicate_stems
        )


class _BrowsableOptions(TypedDict):
    key_fn: Callable[[str], str]
    link_mode: LinkMode
    checksum: bool
    on_file_checked: Callable[[str, bool], None] | None


def check_std_media_source_integrity(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> StdMediaSourceIntegrityResult:
    """Run integrity checks for a single std media source.

    Only runs on std media sources that have an archive directory
    (``std-{name}/``) on disk.
    """
    if not ms.is_std:
        raise ValueError(f"media source '{ms.name}' is not a std media source")

    browsable_opts = _BrowsableOptions(
        key_fn=ms.key_fn,
        link_mode=link_mode,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )
    all_media = IMG_EXTENSIONS | VID_EXTENSIONS
    return StdMediaSourceIntegrityResult(
        browsable_img=check_browsable_dir(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            album_dir / ms.img_dir,
            media_extensions=IMG_EXTENSIONS,
            **browsable_opts,
        ),
        browsable_vid=check_browsable_dir(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
            album_dir / ms.vid_dir,
            media_extensions=VID_EXTENSIONS,
            **browsable_opts,
        ),
        browsable_jpg=check_jpeg_dir(album_dir / ms.img_dir, album_dir / ms.jpg_dir),
        duplicate_stems=tuple(
            dup
            for subdir_name in ms.all_subdirs
            if (album_dir / subdir_name).is_dir()
            for dup in check_duplicate_stems(album_dir / subdir_name, all_media)
        ),
    )
