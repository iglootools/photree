"""Pre-flight checks for album operations."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..fsprotocol import (
    ALBUM_SENTINEL,
    IOS_ALBUM_IMAGE_SUBDIRS,
    IOS_ALBUM_OPTIONAL_SUBDIRS,
    IOS_ALBUM_REQUIRED_SUBDIRS,
    IOS_ALBUM_SUBDIRS,
    IOS_ALBUM_VIDEO_SUBDIRS,
    IOS_DIR,
)
from .exif import check_exiftool_available
from .integrity import IosAlbumIntegrityResult, check_ios_album_integrity
from .naming import (
    AlbumNamingResult,
    check_album_naming,
    check_exif_date_match,
    parse_album_name,
)


def check_sips_available() -> bool:
    """Check whether the macOS ``sips`` tool is on PATH."""
    return shutil.which("sips") is not None


class AlbumType(StrEnum):
    """Type of album directory.

    Detection is currently based on directory structure heuristics.
    In the future, this will be stored as metadata in the album directory.
    """

    IOS = "ios"
    OTHER = "other"


def detect_album_type(album_dir: Path) -> AlbumType:
    """Detect the album type based on directory structure.

    An album is considered iOS if it contains the ``ios/`` subdirectory.
    """
    if (album_dir / IOS_DIR).is_dir():
        return AlbumType.IOS
    else:
        return AlbumType.OTHER


@dataclass(frozen=True)
class AlbumDirCheck:
    """Result of checking an album directory for expected subdirectories."""

    present: tuple[str, ...]
    missing: tuple[str, ...]
    optional_present: tuple[str, ...] = ()
    optional_absent: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return len(self.missing) == 0


def _is_group_present(album_dir: Path, group: tuple[str, ...]) -> bool:
    """Check if all directories in a group are present."""
    return all((album_dir / d).is_dir() for d in group)


def check_ios_album_dir(album_dir: Path) -> AlbumDirCheck:
    """Check which expected iOS album subdirectories are present in *album_dir*.

    At least one directory group must be fully present:
    - Image group: orig-img, main-img, main-jpg
    - Video group: orig-vid, main-vid

    Within present groups, all directories are required.
    Directories from absent groups are reported as optional.
    Optional directories (edit-img, edit-vid) are always informational.
    """
    image_present = _is_group_present(album_dir, IOS_ALBUM_IMAGE_SUBDIRS)
    video_present = _is_group_present(album_dir, IOS_ALBUM_VIDEO_SUBDIRS)

    # Required: directories from groups that are (at least partially) present
    # If a group has some dirs but not all, the missing ones are required
    required = [
        *(
            IOS_ALBUM_IMAGE_SUBDIRS
            if image_present or _has_any(album_dir, IOS_ALBUM_IMAGE_SUBDIRS)
            else ()
        ),
        *(
            IOS_ALBUM_VIDEO_SUBDIRS
            if video_present or _has_any(album_dir, IOS_ALBUM_VIDEO_SUBDIRS)
            else ()
        ),
    ]

    # If neither group is even partially present, both groups are required
    # (to report meaningful missing dirs)
    if not required:
        required = list(IOS_ALBUM_REQUIRED_SUBDIRS)

    # Directories from fully absent groups are optional
    optional_from_groups = [
        *(
            IOS_ALBUM_IMAGE_SUBDIRS
            if not image_present and not _has_any(album_dir, IOS_ALBUM_IMAGE_SUBDIRS)
            else ()
        ),
        *(
            IOS_ALBUM_VIDEO_SUBDIRS
            if not video_present and not _has_any(album_dir, IOS_ALBUM_VIDEO_SUBDIRS)
            else ()
        ),
    ]

    return AlbumDirCheck(
        present=tuple(d for d in required if (album_dir / d).is_dir()),
        missing=tuple(d for d in required if not (album_dir / d).is_dir()),
        optional_present=tuple(
            d
            for d in (*IOS_ALBUM_OPTIONAL_SUBDIRS, *optional_from_groups)
            if (album_dir / d).is_dir()
        ),
        optional_absent=tuple(
            d
            for d in (*IOS_ALBUM_OPTIONAL_SUBDIRS, *optional_from_groups)
            if not (album_dir / d).is_dir()
        ),
    )


def _has_any(album_dir: Path, group: tuple[str, ...]) -> bool:
    """Check if any directory in a group is present."""
    return any((album_dir / d).is_dir() for d in group)


def check_other_album_dir(album_dir: Path) -> AlbumDirCheck:
    """Check a free-form album directory.

    Currently accepts any directory. This will be extended with additional
    checks as the feature evolves.
    """
    return AlbumDirCheck(present=(), missing=())


def check_album_dir(
    album_dir: Path,
    expected: tuple[str, ...] = IOS_ALBUM_SUBDIRS,
) -> AlbumDirCheck:
    """Check which expected subdirectories are present in *album_dir*.

    Used by import commands to check specific directories (e.g. SELECTION_DIR).
    """
    return AlbumDirCheck(
        present=tuple(d for d in expected if (album_dir / d).is_dir()),
        missing=tuple(d for d in expected if not (album_dir / d).is_dir()),
    )


@dataclass(frozen=True)
class AlbumPreflightResult:
    """Structured result of all album preflight checks."""

    sips_available: bool
    exiftool_available: bool
    album_type: AlbumType
    dir_check: AlbumDirCheck
    integrity: IosAlbumIntegrityResult | None = None
    naming: AlbumNamingResult | None = None

    @property
    def success(self) -> bool:
        return (
            self.sips_available
            and self.dir_check.success
            and (self.integrity is None or self.integrity.success)
            and (self.naming is None or self.naming.success)
        )

    @property
    def has_warnings(self) -> bool:
        return (self.integrity is not None and self.integrity.has_warnings) or (
            self.naming is not None and self.naming.has_warnings
        )


def run_album_check(
    album_dir: Path,
    *,
    sips_available: bool,
    exiftool_available: bool,
    checksum: bool = True,
    check_naming_flag: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> AlbumPreflightResult:
    """Run album-specific checks (type detection, dir structure, integrity, naming).

    Accepts ``sips_available`` and ``exiftool_available`` as parameters so
    system checks can be done once for batch operations.
    """
    album_type = detect_album_type(album_dir)

    match album_type:
        case AlbumType.IOS:
            dir_check = check_ios_album_dir(album_dir)
            integrity = check_ios_album_integrity(
                album_dir,
                checksum=checksum,
                on_file_checked=on_file_checked,
            )
        case AlbumType.OTHER:
            dir_check = check_other_album_dir(album_dir)
            integrity = None

    naming = None
    if check_naming_flag:
        issues = check_album_naming(album_dir.name)
        parsed = parse_album_name(album_dir.name)
        exif_check = None
        if exiftool_available and parsed is not None:
            exif_check = check_exif_date_match(album_dir, parsed.date)
        naming = AlbumNamingResult(
            parsed=parsed,
            issues=issues,
            exif_check=exif_check,
        )

    return AlbumPreflightResult(
        sips_available=sips_available,
        exiftool_available=exiftool_available,
        album_type=album_type,
        dir_check=dir_check,
        integrity=integrity,
        naming=naming,
    )


def run_album_preflight(
    album_dir: Path,
    *,
    checksum: bool = True,
    check_naming_flag: bool = True,
    on_file_checked: Callable[[str, bool], None] | None = None,
) -> AlbumPreflightResult:
    """Run all album preflight checks including system checks."""
    return run_album_check(
        album_dir,
        sips_available=check_sips_available(),
        exiftool_available=check_exiftool_available(),
        checksum=checksum,
        check_naming_flag=check_naming_flag,
        on_file_checked=on_file_checked,
    )


def discover_albums(base_dir: Path) -> list[Path]:
    """Recursively discover album directories under *base_dir*.

    Detection rules (first match wins, per directory):
    1. Contains ``ios/`` subdirectory → iOS album
    2. Contains ``.album`` sentinel file → explicit album marker
    3. Leaf directory (no non-hidden subdirectories) → implicit album

    The *base_dir* itself is never returned as an album.
    """
    albums: list[Path] = []

    def walk(directory: Path) -> None:
        if (directory / IOS_DIR).is_dir() or (directory / ALBUM_SENTINEL).is_file():
            albums.append(directory)
            return

        subdirs = sorted(
            child
            for child in directory.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )

        if not subdirs:
            if directory != base_dir:
                albums.append(directory)
            return

        for subdir in subdirs:
            walk(subdir)

    walk(base_dir)
    return albums


def discover_ios_albums(base_dir: Path) -> list[Path]:
    """Recursively discover iOS album directories under *base_dir*."""
    return sorted(
        Path(dirpath)
        for dirpath, _dirnames, _filenames in os.walk(base_dir)
        if detect_album_type(Path(dirpath)) == AlbumType.IOS
    )
