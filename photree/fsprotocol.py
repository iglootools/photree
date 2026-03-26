"""Filesystem naming conventions and shared helpers for album directories."""

import os
import re
from dataclasses import dataclass
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

# ---------------------------------------------------------------------------
# Contributor — a named source of photos within an album
# ---------------------------------------------------------------------------

IOS_DIR_PREFIX = "ios-"
DEFAULT_CONTRIBUTOR = "main"


class ContributorType(StrEnum):
    """How a contributor's photos are stored."""

    IOS = "ios"  # archival (ios-{name}/) + browsable ({name}-img/, etc.)
    PLAIN = "plain"  # browsable only ({name}-img/, {name}-vid/)


@dataclass(frozen=True)
class Contributor:
    """A named source of photos within an album.

    **iOS** contributors have archival directories (under ``ios-{name}/``)
    and browsable directories (``{name}-img/``, ``{name}-vid/``,
    ``{name}-jpg/``).

    **Plain** contributors only have browsable directories.
    """

    name: str  # "main", "bruno"
    contributor_type: ContributorType
    ios_dir: str  # "ios-main" (unused path for plain contributors)
    orig_img_dir: str  # "ios-main/orig-img" (unused path for plain)
    edit_img_dir: str  # "ios-main/edit-img" (unused path for plain)
    orig_vid_dir: str  # "ios-main/orig-vid" (unused path for plain)
    edit_vid_dir: str  # "ios-main/edit-vid" (unused path for plain)
    img_dir: str  # "main-img", "bruno-img"
    vid_dir: str  # "main-vid", "bruno-vid"
    jpg_dir: str  # "main-jpg", "bruno-jpg"

    @property
    def is_ios(self) -> bool:
        return self.contributor_type == ContributorType.IOS

    @property
    def image_subdirs(self) -> tuple[str, ...]:
        """Required image directories for this contributor."""
        if self.is_ios:
            return (self.orig_img_dir, self.img_dir, self.jpg_dir)
        else:
            return (self.img_dir,)

    @property
    def video_subdirs(self) -> tuple[str, ...]:
        """Required video directories for this contributor."""
        if self.is_ios:
            return (self.orig_vid_dir, self.vid_dir)
        else:
            return (self.vid_dir,)

    @property
    def required_subdirs(self) -> tuple[str, ...]:
        """All required subdirectories (images + videos)."""
        return (*self.image_subdirs, *self.video_subdirs)

    @property
    def optional_subdirs(self) -> tuple[str, ...]:
        """Directories only present when edits exist (iOS only)."""
        if self.is_ios:
            return (self.edit_img_dir, self.edit_vid_dir)
        else:
            return ()

    @property
    def all_subdirs(self) -> tuple[str, ...]:
        """All possible subdirectories for this contributor."""
        return (*self.required_subdirs, *self.optional_subdirs)


def ios_contributor(name: str) -> Contributor:
    """Create an iOS :class:`Contributor`."""
    ios = f"{IOS_DIR_PREFIX}{name}"
    return Contributor(
        name=name,
        contributor_type=ContributorType.IOS,
        ios_dir=ios,
        orig_img_dir=f"{ios}/orig-img",
        edit_img_dir=f"{ios}/edit-img",
        orig_vid_dir=f"{ios}/orig-vid",
        edit_vid_dir=f"{ios}/edit-vid",
        img_dir=f"{name}-img",
        vid_dir=f"{name}-vid",
        jpg_dir=f"{name}-jpg",
    )


def plain_contributor(name: str) -> Contributor:
    """Create a plain (non-iOS) :class:`Contributor`.

    The ``ios_dir`` and archival paths are populated but don't exist on disk.
    Code that operates on these dirs handles missing directories gracefully.
    """
    ios = f"{IOS_DIR_PREFIX}{name}"
    return Contributor(
        name=name,
        contributor_type=ContributorType.PLAIN,
        ios_dir=ios,
        orig_img_dir=f"{ios}/orig-img",
        edit_img_dir=f"{ios}/edit-img",
        orig_vid_dir=f"{ios}/orig-vid",
        edit_vid_dir=f"{ios}/edit-vid",
        img_dir=f"{name}-img",
        vid_dir=f"{name}-vid",
        jpg_dir=f"{name}-jpg",
    )


# Backward compat alias — creates an iOS contributor
contributor = ios_contributor

MAIN_CONTRIBUTOR = ios_contributor(DEFAULT_CONTRIBUTOR)


PHOTREE_DIR = ".photree"


def is_album(directory: Path) -> bool:
    """Check if a directory is a photree album.

    A directory is an album if it contains a ``.photree/`` directory
    **and** at least one contributor (iOS or plain).
    """
    return (directory / PHOTREE_DIR).is_dir() and bool(discover_contributors(directory))


def discover_albums(base_dir: Path) -> list[Path]:
    """Recursively discover album directories under *base_dir*.

    A directory is considered an album when it contains:
    1. A ``.photree/`` directory (album marker), **and**
    2. At least one contributor (``ios-{name}/`` or ``{name}-img/``/``{name}-vid/``)

    The *base_dir* itself is never returned as an album.
    """
    albums: list[Path] = []

    def walk(directory: Path) -> None:
        if is_album(directory):
            albums.append(directory)
            return

        subdirs = sorted(
            child
            for child in directory.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )

        for subdir in subdirs:
            walk(subdir)

    walk(base_dir)
    return albums


def discover_contributors(album_dir: Path) -> list[Contributor]:
    """Discover all contributors in an album.

    Scans for:
    1. iOS contributors: ``ios-{name}/`` with ``orig-img/`` or ``orig-vid/``
    2. Plain contributors: ``{name}-img/`` or ``{name}-vid/`` without
       a corresponding ``ios-{name}/`` directory

    Returns contributors sorted with ``main`` first, then alphabetically.
    """
    if not album_dir.is_dir():
        return []

    # 1. Find iOS contributors
    ios_names: set[str] = set()
    ios_contribs: list[Contributor] = []
    for d in album_dir.iterdir():
        if (
            d.is_dir()
            and d.name.startswith(IOS_DIR_PREFIX)
            and ((d / "orig-img").is_dir() or (d / "orig-vid").is_dir())
        ):
            name = d.name.removeprefix(IOS_DIR_PREFIX)
            ios_names.add(name)
            ios_contribs.append(ios_contributor(name))

    # 2. Find plain contributors from {name}-img or {name}-vid dirs
    plain_names: set[str] = set()
    for d in album_dir.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            pass
        elif d.name.endswith("-img") or d.name.endswith("-vid"):
            name = d.name.removesuffix("-img").removesuffix("-vid")
            if name and name not in ios_names and name not in plain_names:
                plain_names.add(name)

    plain_contribs = [plain_contributor(name) for name in plain_names]

    return sorted(
        [*ios_contribs, *plain_contribs],
        key=lambda c: (c.name != DEFAULT_CONTRIBUTOR, c.name),
    )


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

# Preferred formats when multiple variants exist for the same image number.
# DNG (ProRAW) is the highest-quality format, followed by HEIC (native iPhone).
# Handles the iOS edge case where both JPG and HEIC/DNG variants exist
# for the same edited photo (e.g. IMG_E7658.JPG + IMG_E7658.HEIC).
# Tuple (not set) to express priority order: first match wins.
PICTURE_PRIORITY_EXTENSIONS = (".dng", ".heic")

# JPEG conversion — formats sips can convert to JPEG
CONVERT_TO_JPEG_EXTENSIONS = frozenset({".dng", ".heic", ".heif"})
COPY_AS_IS_TO_JPEG_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})


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
