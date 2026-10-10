"""iOS-specific media source integrity checks.

Covers duplicate image numbers, miscategorized files, and the full
iOS media-source integrity check that combines browsable, JPEG, and
sidecar checks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import groupby
from pathlib import Path

from ....common.fs import file_ext, list_files
from ....fsprotocol import LinkMode
from ...store.media_sources import ios_file_prefix, ios_img_number, ios_is_media
from ...store.protocol import (
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    MediaSource,
)
from ..browsable import BrowsableDirCheck, check_browsable_dir
from ..jpeg import JpegCheck, check_jpeg_dir
from .sidecar import SidecarCheck, check_sidecars

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DuplicateNumber:
    """Several media files in *directory* share a prefix and image number.

    E.g. ``IMG_E7658.HEIC`` + ``IMG_E7658.JPG``. *directory* is a directory
    name, as displayed.
    """

    directory: str
    img_number: str
    files: tuple[str, ...]


class MiscategorizedKind(StrEnum):
    EDITED_IN_ORIG = "edited-in-orig"  # IMG_E* media in orig-*/
    EDITED_SIDECAR_IN_ORIG = "edited-sidecar-in-orig"  # IMG_O* in orig-*/
    ORIGINAL_IN_EDIT = "original-in-edit"  # IMG_XXXX media in edit-*/
    ORIGINAL_SIDECAR_IN_EDIT = "original-sidecar-in-edit"  # IMG_XXXX.AAE in edit-*/


@dataclass(frozen=True)
class MiscategorizedFile:
    """*file* sits in *directory* (a directory name) but belongs elsewhere."""

    file: str
    directory: str
    kind: MiscategorizedKind


@dataclass(frozen=True)
class IosMediaSourceIntegrityResult:
    """Integrity check result for a single iOS media source."""

    browsable_img: BrowsableDirCheck
    browsable_vid: BrowsableDirCheck
    browsable_jpg: JpegCheck
    sidecars: SidecarCheck
    duplicate_numbers: tuple[DuplicateNumber, ...] = ()
    miscategorized: tuple[MiscategorizedFile, ...] = ()

    @property
    def success(self) -> bool:
        # missing_sidecars are not checked here: iOS does not always produce
        # AAE sidecars (e.g. no edits applied, older iOS versions), so their
        # absence is informational, not an error.
        # Use has_warnings to detect these; --fatal-warnings promotes them.
        return (
            self.browsable_img.success
            and self.browsable_vid.success
            and self.browsable_jpg.success
            and not self.sidecars.orphan_sidecars
            and not self.duplicate_numbers
            and not self.miscategorized
        )

    @property
    def has_warnings(self) -> bool:
        """True if there are informational warnings (e.g. missing sidecars)."""
        return bool(self.sidecars.missing_sidecars)


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _duplicate_key(
    filename: str, img_extensions: frozenset[str]
) -> tuple[str, str, str]:
    """``(prefix, number, media category)`` — what makes two files duplicates.

    An image and a video with the same prefix and number is a Live Photo, not
    a duplicate, hence the media category.
    """
    media_cat = "img" if file_ext(filename) in img_extensions else "vid"
    return (ios_file_prefix(filename), ios_img_number(filename), media_cat)


def check_duplicate_numbers(
    directory: Path,
    media_extensions: frozenset[str],
    img_extensions: frozenset[str] = frozenset(),
) -> tuple[DuplicateNumber, ...]:
    """Check for duplicate media file numbers within the same prefix category.

    IMG_7552.HEIC + IMG_E7552.HEIC sharing number 7552 is normal (original + edited).
    IMG_E7658.HEIC + IMG_E7658.JPG sharing number 7658 within the same 'E' prefix is a duplicate.
    IMG_0410.HEIC + IMG_0410.MOV sharing number 0410 with different media types
    is a Live Photo, not a duplicate.
    """
    keyed = sorted(
        (
            (_duplicate_key(f, img_extensions), f)
            for f in list_files(directory)
            if file_ext(f) in media_extensions
        ),
    )
    return tuple(
        DuplicateNumber(directory=directory.name, img_number=num, files=files)
        for (_prefix, num, _cat), group in groupby(keyed, key=lambda kf: kf[0])
        if len(files := tuple(f for _, f in group)) > 1
    )


def check_miscategorized_files(
    orig_dir: Path,
    edit_dir: Path,
) -> tuple[MiscategorizedFile, ...]:
    """Check for edited files in orig dirs and original files in edit dirs.

    Orig dirs should contain only original files (IMG_XXXX prefix).
    Edit dirs should contain only edited files (IMG_E/IMG_O prefix).
    """
    orig_files = list_files(orig_dir)
    edit_files = list_files(edit_dir)

    return (
        *[
            MiscategorizedFile(f, orig_dir.name, MiscategorizedKind.EDITED_IN_ORIG)
            for f in orig_files
            if ios_is_media(f) and ios_file_prefix(f) == "E"
        ],
        *[
            MiscategorizedFile(
                f, orig_dir.name, MiscategorizedKind.EDITED_SIDECAR_IN_ORIG
            )
            for f in orig_files
            if ios_file_prefix(f) == "O"
        ],
        *[
            MiscategorizedFile(f, edit_dir.name, MiscategorizedKind.ORIGINAL_IN_EDIT)
            for f in edit_files
            if ios_is_media(f) and ios_file_prefix(f) == ""
        ],
        *[
            MiscategorizedFile(
                f, edit_dir.name, MiscategorizedKind.ORIGINAL_SIDECAR_IN_EDIT
            )
            for f in edit_files
            if not ios_is_media(f) and ios_file_prefix(f) == ""
        ],
    )


def _filter_live_photo_extras(
    browsable_check: BrowsableDirCheck,
    live_photo_vid_filenames: frozenset[str],
) -> BrowsableDirCheck:
    """Return a new BrowsableDirCheck with Live Photo videos removed from extra."""
    return replace(
        browsable_check,
        extra=tuple(
            f for f in browsable_check.extra if f not in live_photo_vid_filenames
        ),
    )


def _detect_live_photo_vid_filenames(
    album_dir: Path, ms: MediaSource
) -> frozenset[str]:
    """Return expected Live Photo video filenames for an iOS media source."""
    from ...live_photo import compute_live_photo_videos, detect_live_photo_keys

    live_keys = detect_live_photo_keys(
        album_dir / ms.orig_img_dir,
        IOS_IMG_EXTENSIONS,
        IOS_VID_EXTENSIONS,
        ms.key_fn,
    )
    if not live_keys:
        return frozenset()
    else:
        videos = compute_live_photo_videos(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
            IOS_VID_EXTENSIONS,
            ms.key_fn,
        )
        return frozenset(name for name, _ in videos)


def _check_browsable(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode,
    checksum: bool,
    on_file_checked: Callable[[str, bool], None] | None,
) -> tuple[BrowsableDirCheck, BrowsableDirCheck]:
    """Browsable img + vid checks for an iOS source."""
    img = check_browsable_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        media_extensions=IOS_IMG_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )
    vid = check_browsable_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        album_dir / ms.vid_dir,
        media_extensions=IOS_VID_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )
    # Filter Live Photo companion videos from the "extra" list — they are
    # expected in the browsable img dir but not matched by IOS_IMG_EXTENSIONS.
    live_videos = _detect_live_photo_vid_filenames(album_dir, ms)
    return _filter_live_photo_extras(img, live_videos), vid


def _check_ios_sidecars(album_dir: Path, ms: MediaSource) -> SidecarCheck:
    heic = check_sidecars(album_dir / ms.orig_img_dir, album_dir / ms.edit_img_dir)
    mov = check_sidecars(album_dir / ms.orig_vid_dir, album_dir / ms.edit_vid_dir)
    return SidecarCheck(
        missing_sidecars=(*heic.missing_sidecars, *mov.missing_sidecars),
        orphan_sidecars=(*heic.orphan_sidecars, *mov.orphan_sidecars),
    )


def _check_ios_duplicates(
    album_dir: Path, ms: MediaSource
) -> tuple[DuplicateNumber, ...]:
    all_media = IOS_IMG_EXTENSIONS | IOS_VID_EXTENSIONS
    return tuple(
        dup
        for subdir_name in ms.all_subdirs
        if (album_dir / subdir_name).is_dir()
        for dup in check_duplicate_numbers(
            album_dir / subdir_name, all_media, IOS_IMG_EXTENSIONS
        )
    )


def check_ios_media_source_integrity(
    album_dir: Path,
    ms: MediaSource,
    *,
    link_mode: LinkMode,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> IosMediaSourceIntegrityResult:
    """Run all integrity checks for a single iOS media source."""
    if not ms.is_ios:
        raise ValueError(f"media source '{ms.name}' is not an iOS media source")

    browsable_img, browsable_vid = _check_browsable(
        album_dir,
        ms,
        link_mode=link_mode,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )
    return IosMediaSourceIntegrityResult(
        browsable_img=browsable_img,
        browsable_vid=browsable_vid,
        browsable_jpg=check_jpeg_dir(album_dir / ms.img_dir, album_dir / ms.jpg_dir),
        sidecars=_check_ios_sidecars(album_dir, ms),
        duplicate_numbers=_check_ios_duplicates(album_dir, ms),
        miscategorized=(
            *check_miscategorized_files(
                album_dir / ms.orig_img_dir, album_dir / ms.edit_img_dir
            ),
            *check_miscategorized_files(
                album_dir / ms.orig_vid_dir, album_dir / ms.edit_vid_dir
            ),
        ),
    )
