"""Album protocol — models, constants, media source types, extensions, and external IDs."""

from __future__ import annotations

import re
import uuid as _uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from textwrap import dedent

from pydantic import Field
from uuid6 import uuid7

from ...common.base58 import base58_decode, base58_encode
from ...fsprotocol import _BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALBUM_YAML = "album.yaml"

SELECTION_DIR = "to-import"

IOS_DIR_PREFIX = "ios-"
STD_DIR_PREFIX = "std-"
DEFAULT_MEDIA_SOURCE = "main"

ALBUM_ID_PREFIX = "album"


# ---------------------------------------------------------------------------
# File extensions
# ---------------------------------------------------------------------------

# All recognized media formats
IMG_EXTENSIONS = frozenset({".dng", ".heic", ".heif", ".jpeg", ".jpg", ".png"})
VID_EXTENSIONS = frozenset({".avi", ".mov", ".mp4", ".wmv"})

# iOS-specific subsets (used by importer, iOS fixes, integrity checks)
IOS_IMG_EXTENSIONS = frozenset({".dng", ".heic", ".jpeg", ".jpg", ".png"})
IOS_VID_EXTENSIONS = frozenset({".mov"})
SIDECAR_EXTENSIONS = frozenset({".aae"})

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
# External ID helpers
# ---------------------------------------------------------------------------


def generate_album_id() -> str:
    """Generate a new UUID v7 string for an album."""
    return str(uuid7())


def format_external_id(type_prefix: str, internal_id: str) -> str:
    """Convert an internal UUID string to ``prefix_base58`` external form."""
    return f"{type_prefix}_{base58_encode(_uuid.UUID(internal_id).bytes)}"


def parse_external_id(external_id: str, expected_prefix: str) -> str:
    """Convert ``prefix_base58`` external form back to a UUID string."""
    prefix, sep, encoded = external_id.partition("_")
    if not sep or prefix != expected_prefix:
        raise ValueError(f"Expected '{expected_prefix}_...' but got '{external_id}'")
    return str(_uuid.UUID(bytes=base58_decode(encoded)))


def format_album_external_id(internal_id: str) -> str:
    """Convenience wrapper for album external IDs."""
    return format_external_id(ALBUM_ID_PREFIX, internal_id)


# ---------------------------------------------------------------------------
# Album naming / date parsing
# ---------------------------------------------------------------------------

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
    ``{name}-vid/``, ``{name}-jpg/``).

    Legacy std sources (pre-migration) may lack the ``std-{name}/``
    archive on disk; code handles missing directories gracefully.
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
        if self.is_ios:
            from ..store.media_sources import img_number

            return img_number
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
    For legacy (pre-migration) albums, the ``std-{name}/`` archive
    directory may not exist on disk; code handles this gracefully.
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
