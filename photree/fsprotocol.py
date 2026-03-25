"""Filesystem naming conventions and shared helpers for album directories."""

import os
import re
from enum import StrEnum
from pathlib import Path
from textwrap import dedent


def display_path(path: Path, cwd: Path) -> Path:
    """Return *path* relative to *cwd* when possible, otherwise unchanged."""
    return path.relative_to(cwd) if path.is_relative_to(cwd) else path


def list_files(directory: Path) -> list[str]:
    """Return regular filenames in *directory*, excluding dotfiles (e.g. .DS_Store).

    Returns an empty list when *directory* does not exist.
    """
    if not directory.is_dir():
        return []
    return sorted(
        f
        for f in os.listdir(directory)
        if not f.startswith(".") and (directory / f).is_file()
    )


class AlbumShareLayout(StrEnum):
    """How an iOS album is exported."""

    MAIN_ONLY = "main-only"
    MAIN_JPG_ONLY = "main-jpg-only"
    FULL = "full"
    FULL_MANAGED = "full-managed"


class LinkMode(StrEnum):
    """How main-dir files reference their source."""

    COPY = "copy"
    HARDLINK = "hardlink"
    SYMLINK = "symlink"


class ShareDirectoryLayout(StrEnum):
    """How albums are organized within the share directory."""

    FLAT = "flat"
    ALBUMS = "albums"


SHARE_SENTINEL = ".photree-share"
ALBUM_SENTINEL = ".album"

# Date regex for naming convention validation.
# Single dates: YYYY, YYYY-MM, YYYY-MM-DD
# Ranges: any precision -- any precision (e.g. YYYY--YYYY-MM, YYYY-MM-DD--YYYY-MM-DD)
_DATE_PART = r"\d{4}(?:-\d{2}(?:-\d{2})?)?"
ALBUM_DATE_RE = re.compile(rf"^({_DATE_PART}(?:--{_DATE_PART})?) - ")

_ALBUM_DATE_RE = re.compile(r"^(\d{4})-\d{2}-\d{2}")


def parse_album_year(album_name: str) -> str:
    """Extract the year from an album name starting with ``YYYY-MM-DD``.

    Raises :class:`ValueError` when the name does not match.
    """
    m = _ALBUM_DATE_RE.match(album_name)
    if m is None:
        raise ValueError(
            dedent(f"""\
            album name "{album_name}" does not start with YYYY-MM-DD.

            The "albums" share layout organizes exports by year, parsed from
            the album directory name. Expected naming convention:
            "YYYY-MM-DD - <Title>" (e.g. "2024-06-15 - Summer Vacation").""")
        )
    return m.group(1)


# Input
SELECTION_DIR = "to-import"

# iOS-internal directories (archival, under ios/)
IOS_DIR = "ios"
ORIG_IMG_DIR = f"{IOS_DIR}/orig-img"
EDIT_IMG_DIR = f"{IOS_DIR}/edit-img"
ORIG_VID_DIR = f"{IOS_DIR}/orig-vid"
EDIT_VID_DIR = f"{IOS_DIR}/edit-vid"

# Browsable directories (top-level, no sidecars)
MAIN_IMG_DIR = "main-img"
MAIN_JPG_DIR = "main-jpg"
MAIN_VID_DIR = "main-vid"

# File extensions
IMG_EXTENSIONS = frozenset({".dng", ".heic", ".jpeg", ".jpg", ".png"})
MOV_EXTENSIONS = frozenset({".mov"})
SIDECAR_EXTENSIONS = frozenset({".aae"})

# Preferred formats when multiple variants exist for the same image number.
# DNG (ProRAW) is the highest-quality format, followed by HEIC (native iPhone).
# Handles the iOS edge case where both JPG and HEIC/DNG variants exist
# for the same edited photo (e.g. IMG_E7658.JPG + IMG_E7658.HEIC).
# Tuple (not set) to express priority order: first match wins.
PICTURE_PRIORITY_EXTENSIONS = (".dng", ".heic")

# JPEG conversion — extensions that sips can convert to JPEG
CONVERT_TO_JPEG_EXTENSIONS = frozenset({".dng", ".heic"})
COPY_AS_IS_TO_JPEG_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

# iOS album: directory groups — at least one group must be fully present
IOS_ALBUM_IMAGE_SUBDIRS = (ORIG_IMG_DIR, MAIN_IMG_DIR, MAIN_JPG_DIR)
IOS_ALBUM_VIDEO_SUBDIRS = (ORIG_VID_DIR, MAIN_VID_DIR)

# All required subdirectories (union of all groups, for reference)
IOS_ALBUM_REQUIRED_SUBDIRS = (*IOS_ALBUM_IMAGE_SUBDIRS, *IOS_ALBUM_VIDEO_SUBDIRS)

# iOS album: optional subdirectories (only present if some files had edits)
IOS_ALBUM_OPTIONAL_SUBDIRS = (
    EDIT_IMG_DIR,
    EDIT_VID_DIR,
)

# iOS album: all possible subdirectories
IOS_ALBUM_SUBDIRS = (*IOS_ALBUM_REQUIRED_SUBDIRS, *IOS_ALBUM_OPTIONAL_SUBDIRS)


# ---------------------------------------------------------------------------
# Media file helpers
# ---------------------------------------------------------------------------


def file_ext(filename: str) -> str:
    """Return the lowercased file extension (e.g. ``".heic"``)."""
    return Path(filename).suffix.lower()


def img_number(filename: str) -> str:
    """Extract the numeric portion of a filename (e.g. ``"0410"`` from ``"IMG_0410.HEIC"``)."""
    return "".join(c for c in filename if c.isdigit())


def pick_media_priority(candidates: list[str]) -> str:
    """Pick the highest-priority file from candidates (DNG > HEIC > others)."""
    return next(
        (
            f
            for ext in PICTURE_PRIORITY_EXTENSIONS
            for f in candidates
            if file_ext(f) == ext
        ),
        candidates[0],
    )


def _group_by_number(
    files: list[str], media_extensions: frozenset[str]
) -> dict[str, list[str]]:
    """Group media files by their numeric ID."""
    groups: dict[str, list[str]] = {}
    for f in files:
        if file_ext(f) in media_extensions:
            groups.setdefault(img_number(f), []).append(f)
    return groups


def dedup_media_dict(
    files: list[str], media_extensions: frozenset[str]
) -> dict[str, str]:
    """Build a number→filename dict, preferring DNG > HEIC when duplicates exist.

    Handles an undocumented iOS edge case where Image Capture exports multiple
    format variants for the same numeric ID (e.g. IMG_E7658.JPG + IMG_E7658.HEIC).
    This can happen with airdrops, photo downloads, screenshots, or similar use
    cases that share a numeric ID with a camera-taken photo. The priority order
    (DNG > HEIC > others) picks the highest-quality format.
    """
    return {
        num: (pick_media_priority(candidates) if len(candidates) > 1 else candidates[0])
        for num, candidates in _group_by_number(files, media_extensions).items()
    }
