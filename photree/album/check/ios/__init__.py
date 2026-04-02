"""iOS-specific album integrity checks.

Covers duplicate image numbers, miscategorized files, and the full
iOS media-source integrity check that combines browsable, JPEG, and
sidecar checks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ....common.fs import file_ext, list_files
from ...store.media_sources import ios_file_prefix, ios_img_number, ios_is_media
from ...store.media_sources_discovery import discover_media_sources
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
class IosAlbumIntegrityResult:
    """Full integrity check result for an iOS album."""

    browsable_img: BrowsableDirCheck
    browsable_vid: BrowsableDirCheck
    browsable_jpg: JpegCheck
    sidecars: SidecarCheck
    duplicate_numbers: tuple[str, ...] = ()
    miscategorized: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class IosAlbumFullIntegrityResult:
    """Full integrity check result across all contributors."""

    by_media_source: tuple[tuple[MediaSource, IosAlbumIntegrityResult], ...]

    @property
    def success(self) -> bool:
        return all(result.success for _, result in self.by_media_source)

    @property
    def has_warnings(self) -> bool:
        return any(result.has_warnings for _, result in self.by_media_source)


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def check_duplicate_numbers(
    directory: Path, media_extensions: frozenset[str]
) -> tuple[str, ...]:
    """Check for duplicate media file numbers within the same prefix category.

    IMG_7552.HEIC + IMG_E7552.HEIC sharing number 7552 is normal (original + edited).
    IMG_E7658.HEIC + IMG_E7658.JPG sharing number 7658 within the same 'E' prefix is a duplicate.
    """
    files = list_files(directory)
    # Group by (prefix, number) — only flag duplicates within the same prefix
    by_prefix_number: dict[tuple[str, str], list[str]] = {}
    for f in files:
        if file_ext(f) in media_extensions:
            key = (ios_file_prefix(f), ios_img_number(f))
            by_prefix_number.setdefault(key, []).append(f)

    return tuple(
        f"{directory.name}/: number {num} has multiple media files "
        f"with same prefix: {', '.join(candidates)}"
        for (prefix, num), candidates in sorted(by_prefix_number.items())
        if len(candidates) > 1
    )


def check_miscategorized_files(
    orig_dir: Path,
    edit_dir: Path,
) -> tuple[str, ...]:
    """Check for edited files in orig dirs and original files in edit dirs.

    Orig dirs should contain only original files (IMG_XXXX prefix).
    Edit dirs should contain only edited files (IMG_E/IMG_O prefix).
    """
    orig_files = list_files(orig_dir)
    edit_files = list_files(edit_dir)

    return tuple(
        [
            *[
                f"{f} in {orig_dir.name}/ looks like an edited file (IMG_E prefix)"
                for f in sorted(orig_files)
                if ios_is_media(f) and ios_file_prefix(f) == "E"
            ],
            *[
                f"{f} in {orig_dir.name}/ looks like an edited sidecar (IMG_O prefix)"
                for f in sorted(orig_files)
                if ios_file_prefix(f) == "O"
            ],
            *[
                f"{f} in {edit_dir.name}/ looks like an original file (no E/O prefix)"
                for f in sorted(edit_files)
                if ios_is_media(f) and ios_file_prefix(f) == ""
            ],
            *[
                f"{f} in {edit_dir.name}/ looks like an original sidecar (no E/O prefix)"
                for f in sorted(edit_files)
                if not ios_is_media(f) and ios_file_prefix(f) == ""
            ],
        ]
    )


def check_ios_media_source_integrity(
    album_dir: Path,
    ms: MediaSource,
    *,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> IosAlbumIntegrityResult:
    """Run all integrity checks for a single media source within an iOS album."""
    assert ms.is_ios, "integrity checks require an iOS media source"
    browsable_img = check_browsable_dir(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
        album_dir / ms.img_dir,
        media_extensions=IOS_IMG_EXTENSIONS,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )

    browsable_vid = check_browsable_dir(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
        album_dir / ms.vid_dir,
        media_extensions=IOS_VID_EXTENSIONS,
        checksum=checksum,
        on_file_checked=on_file_checked,
    )

    jpeg = check_jpeg_dir(
        album_dir / ms.img_dir,
        album_dir / ms.jpg_dir,
    )

    heic_sidecars = check_sidecars(
        album_dir / ms.orig_img_dir,
        album_dir / ms.edit_img_dir,
    )
    mov_sidecars = check_sidecars(
        album_dir / ms.orig_vid_dir,
        album_dir / ms.edit_vid_dir,
    )
    sidecars = SidecarCheck(
        missing_sidecars=(
            *heic_sidecars.missing_sidecars,
            *mov_sidecars.missing_sidecars,
        ),
        orphan_sidecars=(
            *heic_sidecars.orphan_sidecars,
            *mov_sidecars.orphan_sidecars,
        ),
    )

    all_media = IOS_IMG_EXTENSIONS | IOS_VID_EXTENSIONS
    duplicate_numbers = tuple(
        w
        for subdir_name in ms.all_subdirs
        if (album_dir / subdir_name).is_dir()
        for w in check_duplicate_numbers(album_dir / subdir_name, all_media)
    )

    miscategorized = (
        *check_miscategorized_files(
            album_dir / ms.orig_img_dir,
            album_dir / ms.edit_img_dir,
        ),
        *check_miscategorized_files(
            album_dir / ms.orig_vid_dir,
            album_dir / ms.edit_vid_dir,
        ),
    )

    return IosAlbumIntegrityResult(
        browsable_img=browsable_img,
        browsable_vid=browsable_vid,
        browsable_jpg=jpeg,
        sidecars=sidecars,
        duplicate_numbers=duplicate_numbers,
        miscategorized=miscategorized,
    )


def check_ios_album_integrity(
    album_dir: Path,
    *,
    checksum: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> IosAlbumFullIntegrityResult:
    """Run integrity checks for all iOS media sources in an album."""
    ios_sources = [ms for ms in discover_media_sources(album_dir) if ms.is_ios]
    return IosAlbumFullIntegrityResult(
        by_media_source=tuple(
            (
                ms,
                check_ios_media_source_integrity(
                    album_dir,
                    ms,
                    checksum=checksum,
                    on_file_checked=on_file_checked,
                ),
            )
            for ms in ios_sources
        )
    )
