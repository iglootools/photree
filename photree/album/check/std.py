"""Integrity checks specific to std media sources."""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from typing import TypedDict

from photree.album.check.browsable import BrowsableDirCheck, check_browsable_dir
from photree.album.check.jpeg import JpegCheck, check_jpeg_dir
from photree.album.formats import IMG_EXTENSIONS, VID_EXTENSIONS
from photree.album.store.media_source import (
    MediaSource,
    MediaSourceType,
    WrongMediaSourceTypeError,
)
from photree.common.fs import file_ext, list_files
from photree.common.progress import FileEnd
from photree.foundation.linking import LinkMode


@dataclass(frozen=True)
class DuplicateStem:
    """
    Several media files in *directory* share *stem* (e.g. ``a.heic`` + ``a.jpg``).

    Stems are compared ignoring case, and *stem* is the case-folded form.
    *directory* is the directory's name relative to its parent (``orig``,
    ``orig-img``, ...), which is how the formatters display it.
    """

    directory: str
    stem: str
    files: tuple[str, ...]


def folded_stem(filename: str) -> str:
    """
    Return the stem of *filename*, case-folded.

    Std stems are compared ignoring case: on a case-insensitive filesystem,
    the default on macOS, ``Photo.HEIC`` converts to ``Photo.jpg`` in the
    JPEG dir, the same file there as a copied ``photo.jpg``, so one
    overwrites the other.
    """
    return Path(filename).stem.casefold()


def check_duplicate_stems(
    directory: Path,
    media_extensions: frozenset[str],
) -> tuple[DuplicateStem, ...]:
    """Find the media files in *directory* whose stems match, ignoring case."""
    media = sorted(
        (f for f in list_files(directory) if file_ext(f) in media_extensions),
        key=folded_stem,
    )
    return tuple(
        DuplicateStem(directory=directory.name, stem=key, files=files)
        for key, group in groupby(media, key=folded_stem)
        if len(files := tuple(group)) > 1
    )


@dataclass(frozen=True)
class StdMediaSourceIntegrityResult:
    """The outcome of every integrity check on one std media source."""

    browsable_img: BrowsableDirCheck
    browsable_vid: BrowsableDirCheck
    browsable_jpg: JpegCheck
    duplicate_stems: tuple[DuplicateStem, ...] = ()

    @property
    def success(self) -> bool:
        """Return whether the browsable and JPEG checks passed and no stem repeats."""
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
    on_file_checked: FileEnd | None


def check_std_media_source_integrity(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode,
    checksum: bool = True,
    on_file_checked: FileEnd | None = None,
) -> StdMediaSourceIntegrityResult:
    """
    Check a std media source's archive against its browsable dirs.

    Only runs on std media sources that have an archive directory
    (``std-{name}/``) on disk.
    """
    if not ms.is_std:
        raise WrongMediaSourceTypeError(ms.name, MediaSourceType.STD)

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
