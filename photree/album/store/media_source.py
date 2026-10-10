"""MediaSource — a named source of photos within an album.

Holds the model, its two kinds (iOS, std), the archive/browsable directory
names each kind lays out, and the key functions that identify a media item
within a source (image number for iOS, filename stem for std).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

IOS_DIR_PREFIX = "ios-"
STD_DIR_PREFIX = "std-"
DEFAULT_MEDIA_SOURCE = "main"


# ---------------------------------------------------------------------------
# Key functions
# ---------------------------------------------------------------------------

KeyFn = Callable[[str], str]
"""Key-extraction function: maps a filename to a matching key."""


def ios_img_number(filename: str) -> str:
    """Extract the numeric portion of a filename (e.g. ``"0410"`` from ``"IMG_0410.HEIC"``)."""
    return "".join(c for c in filename if c.isdigit())


def stem_key(filename: str) -> str:
    """Extract filename stem (name without extension) as a matching key."""
    return Path(filename).stem


# ---------------------------------------------------------------------------
# MediaSource
# ---------------------------------------------------------------------------


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
    def key_fn(self) -> KeyFn:
        """Key-extraction function for matching files across directories.

        iOS sources match by image number (digits extracted from filename).
        Std sources match by filename stem.
        """
        match self.media_source_type:
            case MediaSourceType.IOS:
                return ios_img_number
            case MediaSourceType.STD:
                return stem_key

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
