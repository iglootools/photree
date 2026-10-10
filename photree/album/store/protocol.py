"""Album protocol — models, constants, media source types, and extensions."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from ...fsprotocol import _BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALBUM_YAML = "album.yaml"
MEDIA_IDS_DIR = "media-ids"
CACHE_DIR = "cache"

# Import staging directories are named ``to-import-{ios,std}-<media-source>``.
# Each targets a specific media source: iOS sources use the directory (and an
# optional sibling ``.csv``) as a selection list matched against Image Capture;
# std sources place their files directly under ``orig/`` and ``edit/``.
TO_IMPORT_PREFIX = "to-import-"

IOS_DIR_PREFIX = "ios-"
STD_DIR_PREFIX = "std-"
DEFAULT_MEDIA_SOURCE = "main"


# ---------------------------------------------------------------------------
# File extensions
# ---------------------------------------------------------------------------

# All recognized media formats
IMG_EXTENSIONS = frozenset({".dng", ".heic", ".heif", ".jpeg", ".jpg", ".png"})
VID_EXTENSIONS = frozenset({".avi", ".mov", ".mp4", ".wmv"})

# iOS-specific subsets (used by importer, iOS fixes, integrity checks)
IOS_IMG_EXTENSIONS = frozenset({".dng", ".heic", ".heif", ".jpeg", ".jpg", ".png"})
IOS_VID_EXTENSIONS = frozenset({".mov"})
IOS_SIDECAR_EXTENSIONS = frozenset({".aae"})

# JPEG conversion — formats sips can convert to JPEG
CONVERT_TO_JPEG_EXTENSIONS = frozenset({".dng", ".heic", ".heif"})
COPY_AS_IS_TO_JPEG_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

# Preferred formats when multiple variants exist for the same key.
# DNG (ProRAW) is the highest-quality format, followed by HEIC (native iPhone).
# Tuple (not set) to express priority order: first match wins.
PICTURE_PRIORITY_EXTENSIONS = (".dng", ".heic")


# ---------------------------------------------------------------------------
# Metadata model
# ---------------------------------------------------------------------------


class AlbumMetadata(_BaseModel):
    """Per-album metadata stored in ``.photree/album.yaml``."""

    id: str = Field(description="UUID v7 identifying the album.")


# ---------------------------------------------------------------------------
# Album naming / date parsing
# ---------------------------------------------------------------------------

# Date regex for naming convention validation.
# Single dates: YYYY, YYYY-MM, YYYY-MM-DD
# Ranges: any precision -- any precision (e.g. YYYY--YYYY-MM, YYYY-MM-DD--YYYY-MM-DD)
_DATE_PART = r"\d{4}(?:-\d{2}(?:-\d{2})?)?"
ALBUM_DATE_RE = re.compile(rf"^({_DATE_PART}(?:--{_DATE_PART})?) - ")

# The year of any album date precision: "2024 - ...", "2024-06", "2024-06-15".
_ALBUM_YEAR_RE = re.compile(r"^(\d{4})(?!\d)")
_ALBUM_MONTH_RE = re.compile(r"^(\d{4}-\d{2})(?!\d)")


class AlbumDatePrefixKind(StrEnum):
    """Which date prefix an album name was expected to start with."""

    YEAR = "year"
    """``YYYY`` (any album date precision)."""
    MONTH = "month"
    """``YYYY-MM`` (month or day precision, or a range starting with one)."""


class AlbumDatePrefixError(ValueError):
    """An album name lacks the date prefix needed to place it by year/month."""

    def __init__(self, album_name: str, kind: AlbumDatePrefixKind) -> None:
        expected = "YYYY" if kind is AlbumDatePrefixKind.YEAR else "YYYY-MM"
        super().__init__(
            f'album name "{album_name}" does not start with a {expected} date;'
            ' expected "DATE - <Title>" (e.g. "2024-06-15 - Summer Vacation")'
        )
        self.album_name = album_name
        self.kind = kind


def parse_album_year(album_name: str) -> str:
    """Extract the ``YYYY`` year from an album name's date prefix.

    Any album date precision works (``2024``, ``2024-06``, ``2024-06-15``,
    ranges): the year is the start year. Raises :class:`AlbumDatePrefixError`
    when the name does not start with a year.
    """
    m = _ALBUM_YEAR_RE.match(album_name)
    if m is None:
        raise AlbumDatePrefixError(album_name, AlbumDatePrefixKind.YEAR)
    else:
        return m.group(1)


def parse_album_month(album_name: str) -> str:
    """Extract the ``YYYY-MM`` month from an album name.

    For date ranges (``YYYY-MM-DD--YYYY-MM-DD``), the start month is returned
    (the prefix is matched). Raises :class:`AlbumDatePrefixError` when the
    name does not start with at least a ``YYYY-MM`` date.
    """
    m = _ALBUM_MONTH_RE.match(album_name)
    if m is None:
        raise AlbumDatePrefixError(album_name, AlbumDatePrefixKind.MONTH)
    else:
        return m.group(1)


# ---------------------------------------------------------------------------
# MediaSource — a named source of photos within an album
# ---------------------------------------------------------------------------

_KeyFn = Callable[[str], str]
"""Key-extraction function: maps a filename to a matching key."""


def _stem_key(filename: str) -> str:
    """Extract filename stem (name without extension) as a matching key."""
    return Path(filename).stem


class MediaSourceType(StrEnum):
    """How a media source's photos are stored."""

    IOS = "ios"  # archival (ios-{name}/) + browsable ({name}-img/, etc.)
    STD = "std"  # archival (std-{name}/) + browsable ({name}-img/, etc.)


@dataclass(frozen=True)
class MediaSource:
    """A named source of photos within an album.

    Both **iOS** and **std** (standard) media sources have archival
    directories (under ``ios-{name}/`` or ``std-{name}/``) with identical
    internal structure (``orig-img/``, ``edit-img/``, ``orig-vid/``,
    ``edit-vid/``), plus browsable directories (``{name}-img/``,
    ``{name}-vid/``, ``{name}-jpg/``). The browsable directories are derived
    from the archive and rebuilt by refresh.
    """

    name: str  # "main", "bruno"
    media_source_type: MediaSourceType
    archive_dir: str  # "ios-main" or "std-main"
    orig_img_dir: str  # "{archive}/orig-img"
    edit_img_dir: str  # "{archive}/edit-img"
    orig_vid_dir: str  # "{archive}/orig-vid"
    edit_vid_dir: str  # "{archive}/edit-vid"
    img_dir: str  # "main-img", "bruno-img"
    vid_dir: str  # "main-vid", "bruno-vid"
    jpg_dir: str  # "main-jpg", "bruno-jpg"

    @property
    def is_ios(self) -> bool:
        return self.media_source_type == MediaSourceType.IOS

    @property
    def is_std(self) -> bool:
        return self.media_source_type == MediaSourceType.STD

    @property
    def key_fn(self) -> _KeyFn:
        """Key-extraction function for matching files across directories.

        iOS sources match by image number (digits extracted from filename).
        Std sources match by filename stem.
        """
        match self.media_source_type:
            case MediaSourceType.IOS:
                from ..store.media_sources import ios_img_number

                return ios_img_number
            case MediaSourceType.STD:
                return _stem_key

    @property
    def image_variant_dirs(self) -> tuple[str, ...]:
        """All directories where image variants may live (archive + browsable)."""
        return (self.orig_img_dir, self.edit_img_dir, self.img_dir, self.jpg_dir)

    @property
    def video_variant_dirs(self) -> tuple[str, ...]:
        """All directories where video variants may live (archive + browsable)."""
        return (self.orig_vid_dir, self.edit_vid_dir, self.vid_dir)

    @property
    def image_subdirs(self) -> tuple[str, ...]:
        """Required image directories for this media source."""
        return (self.orig_img_dir, self.img_dir, self.jpg_dir)

    @property
    def video_subdirs(self) -> tuple[str, ...]:
        """Required video directories for this media source."""
        return (self.orig_vid_dir, self.vid_dir)

    @property
    def required_subdirs(self) -> tuple[str, ...]:
        """All required subdirectories (images + videos)."""
        return (*self.image_subdirs, *self.video_subdirs)

    @property
    def optional_subdirs(self) -> tuple[str, ...]:
        """Directories only present when edits exist."""
        return (self.edit_img_dir, self.edit_vid_dir)

    @property
    def all_subdirs(self) -> tuple[str, ...]:
        """All possible subdirectories for this media source."""
        return (*self.required_subdirs, *self.optional_subdirs)


def ios_media_source(name: str) -> MediaSource:
    """Create an iOS :class:`MediaSource`."""
    archive = f"{IOS_DIR_PREFIX}{name}"
    return MediaSource(
        name=name,
        media_source_type=MediaSourceType.IOS,
        archive_dir=archive,
        orig_img_dir=f"{archive}/orig-img",
        edit_img_dir=f"{archive}/edit-img",
        orig_vid_dir=f"{archive}/orig-vid",
        edit_vid_dir=f"{archive}/edit-vid",
        img_dir=f"{name}-img",
        vid_dir=f"{name}-vid",
        jpg_dir=f"{name}-jpg",
    )


def std_media_source(name: str) -> MediaSource:
    """Create a standard (non-iOS) :class:`MediaSource`.

    The archive directory structure is identical to iOS
    (``orig-img/``, ``edit-img/``, ``orig-vid/``, ``edit-vid/``).
    Std sources match files by filename stem and skip iOS-specific
    integrity checks and fixes.
    """
    archive = f"{STD_DIR_PREFIX}{name}"
    return MediaSource(
        name=name,
        media_source_type=MediaSourceType.STD,
        archive_dir=archive,
        orig_img_dir=f"{archive}/orig-img",
        edit_img_dir=f"{archive}/edit-img",
        orig_vid_dir=f"{archive}/orig-vid",
        edit_vid_dir=f"{archive}/edit-vid",
        img_dir=f"{name}-img",
        vid_dir=f"{name}-vid",
        jpg_dir=f"{name}-jpg",
    )


MAIN_MEDIA_SOURCE = ios_media_source(DEFAULT_MEDIA_SOURCE)


# ---------------------------------------------------------------------------
# Import staging directory names
# ---------------------------------------------------------------------------


def ios_import_dir(name: str) -> str:
    """Return the iOS import staging dir name (e.g. ``to-import-ios-main``)."""
    return f"{TO_IMPORT_PREFIX}{MediaSourceType.IOS}-{name}"


def ios_import_csv(name: str) -> str:
    """Return the iOS import CSV name (e.g. ``to-import-ios-main.csv``)."""
    return f"{ios_import_dir(name)}.csv"


def std_import_dir(name: str) -> str:
    """Return the std import staging dir name (e.g. ``to-import-std-nelu``)."""
    return f"{TO_IMPORT_PREFIX}{MediaSourceType.STD}-{name}"
