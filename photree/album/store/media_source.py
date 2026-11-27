"""
MediaSource — a named source of photos within an album.

Holds the model, its two kinds (iOS, std), the archive/browsable directory
names each kind lays out, the media extensions each kind holds, and the key
functions that identify a media item within a source (image number for iOS,
filename stem for std).
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.formats import (
    IMG_EXTENSIONS,
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    VID_EXTENSIONS,
)

IOS_DIR_PREFIX = "ios-"
STD_DIR_PREFIX = "std-"
DEFAULT_MEDIA_SOURCE = "main"


type KeyFn = Callable[[str], str]
"""Key-extraction function: maps a filename to a matching key."""


def ios_img_number(filename: str) -> str:
    """
    Extract the numeric portion of a filename.

    For example ``"0410"`` from ``"IMG_0410.HEIC"``.
    """
    return "".join(c for c in filename if c.isdigit())


def stem_key(filename: str) -> str:
    """Return the stem of *filename*, the key of a std media item."""
    return Path(filename).stem


class MediaSourceType(StrEnum):
    """How a media source's photos are stored."""

    IOS = "ios"  # archival (ios-{name}/) + browsable ({name}-img/, etc.)
    STD = "std"  # archival (std-{name}/) + browsable ({name}-img/, etc.)


class WrongMediaSourceTypeError(ValueError):
    """A media source of one type was handed to code that handles only the other."""

    def __init__(self, media_source: str, expected: MediaSourceType) -> None:
        """Build the error from the media source's name and the type the code needs."""
        self.media_source = media_source
        self.expected = expected
        article = {MediaSourceType.IOS: "an iOS", MediaSourceType.STD: "a std"}
        super().__init__(
            f"media source '{media_source}' is not {article[expected]} media source",
        )


@dataclass(frozen=True)
class MediaSource:
    """
    A named source of photos within an album.

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
        """Tell whether this is an iOS media source."""
        return self.media_source_type == MediaSourceType.IOS

    @property
    def is_std(self) -> bool:
        """Tell whether this is a std media source."""
        return self.media_source_type == MediaSourceType.STD

    @property
    def key_fn(self) -> KeyFn:
        """
        Return the function that matches files across directories.

        IOS sources match by image number (digits extracted from filename).
        Std sources match by filename stem.
        """
        match self.media_source_type:
            case MediaSourceType.IOS:
                return ios_img_number
            case MediaSourceType.STD:
                return stem_key

    @property
    def img_extensions(self) -> frozenset[str]:
        """Return the extensions of the images this source holds."""
        match self.media_source_type:
            case MediaSourceType.IOS:
                return IOS_IMG_EXTENSIONS
            case MediaSourceType.STD:
                return IMG_EXTENSIONS

    @property
    def vid_extensions(self) -> frozenset[str]:
        """
        Return the extensions of the videos this source holds.

        An iOS source holds only ``.mov``, what an iPhone records: any other
        video in its archive is not one of its media items.
        """
        match self.media_source_type:
            case MediaSourceType.IOS:
                return IOS_VID_EXTENSIONS
            case MediaSourceType.STD:
                return VID_EXTENSIONS

    @property
    def media_extensions(self) -> frozenset[str]:
        """Return the extensions of every media item this source holds."""
        return self.img_extensions | self.vid_extensions

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
        """Return the original, browsable and JPEG image directories."""
        return (self.orig_img_dir, self.img_dir, self.jpg_dir)

    @property
    def video_subdirs(self) -> tuple[str, ...]:
        """Return the original and browsable video directories."""
        return (self.orig_vid_dir, self.vid_dir)

    @property
    def required_subdirs(self) -> tuple[str, ...]:
        """Return the image and video directories every media source has."""
        return (*self.image_subdirs, *self.video_subdirs)

    @property
    def optional_subdirs(self) -> tuple[str, ...]:
        """Directories only present when edits exist."""
        return (self.edit_img_dir, self.edit_vid_dir)

    @property
    def all_subdirs(self) -> tuple[str, ...]:
        """Return the required directories followed by the edit-only ones."""
        return (*self.required_subdirs, *self.optional_subdirs)


def ios_media_source(name: str) -> MediaSource:
    """Return the iOS media source named *name*, archived under ``ios-{name}/``."""
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
    """
    Return a std media source.

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
