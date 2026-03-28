"""Filesystem naming conventions and shared helpers for album directories."""

import os
import re
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from textwrap import dedent

from rich.console import Console

from .uiconventions import CHECK


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
    """How an album is exported."""

    MAIN_JPG = "main-jpg"
    MAIN = "main"
    ALL = "all"


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
# MediaSource — a named source of photos within an album
# ---------------------------------------------------------------------------

IOS_DIR_PREFIX = "ios-"
DEFAULT_MEDIA_SOURCE = "main"


class MediaSourceType(StrEnum):
    """How a media source's photos are stored."""

    IOS = "ios"  # archival (ios-{name}/) + browsable ({name}-img/, etc.)
    PLAIN = "plain"  # browsable only ({name}-img/, {name}-vid/)


@dataclass(frozen=True)
class MediaSource:
    """A named source of photos within an album.

    **iOS** media sources have archival directories (under ``ios-{name}/``)
    and browsable directories (``{name}-img/``, ``{name}-vid/``,
    ``{name}-jpg/``).

    **Plain** media sources only have browsable directories.
    """

    name: str  # "main", "bruno"
    media_source_type: MediaSourceType
    ios_dir: str  # "ios-main" (unused path for plain media sources)
    orig_img_dir: str  # "ios-main/orig-img" (unused path for plain)
    edit_img_dir: str  # "ios-main/edit-img" (unused path for plain)
    orig_vid_dir: str  # "ios-main/orig-vid" (unused path for plain)
    edit_vid_dir: str  # "ios-main/edit-vid" (unused path for plain)
    img_dir: str  # "main-img", "bruno-img"
    vid_dir: str  # "main-vid", "bruno-vid"
    jpg_dir: str  # "main-jpg", "bruno-jpg"

    @property
    def is_ios(self) -> bool:
        return self.media_source_type == MediaSourceType.IOS

    @property
    def image_subdirs(self) -> tuple[str, ...]:
        """Required image directories for this media source."""
        if self.is_ios:
            return (self.orig_img_dir, self.img_dir, self.jpg_dir)
        else:
            return (self.img_dir, self.jpg_dir)

    @property
    def video_subdirs(self) -> tuple[str, ...]:
        """Required video directories for this media source."""
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
        """All possible subdirectories for this media source."""
        return (*self.required_subdirs, *self.optional_subdirs)


def ios_media_source(name: str) -> MediaSource:
    """Create an iOS :class:`MediaSource`."""
    ios = f"{IOS_DIR_PREFIX}{name}"
    return MediaSource(
        name=name,
        media_source_type=MediaSourceType.IOS,
        ios_dir=ios,
        orig_img_dir=f"{ios}/orig-img",
        edit_img_dir=f"{ios}/edit-img",
        orig_vid_dir=f"{ios}/orig-vid",
        edit_vid_dir=f"{ios}/edit-vid",
        img_dir=f"{name}-img",
        vid_dir=f"{name}-vid",
        jpg_dir=f"{name}-jpg",
    )


def plain_media_source(name: str) -> MediaSource:
    """Create a plain (non-iOS) :class:`MediaSource`.

    The ``ios_dir`` and archival paths are populated but don't exist on disk.
    Code that operates on these dirs handles missing directories gracefully.
    """
    ios = f"{IOS_DIR_PREFIX}{name}"
    return MediaSource(
        name=name,
        media_source_type=MediaSourceType.PLAIN,
        ios_dir=ios,
        orig_img_dir=f"{ios}/orig-img",
        edit_img_dir=f"{ios}/edit-img",
        orig_vid_dir=f"{ios}/orig-vid",
        edit_vid_dir=f"{ios}/edit-vid",
        img_dir=f"{name}-img",
        vid_dir=f"{name}-vid",
        jpg_dir=f"{name}-jpg",
    )


MAIN_MEDIA_SOURCE = ios_media_source(DEFAULT_MEDIA_SOURCE)


PHOTREE_DIR = ".photree"


def is_album(directory: Path) -> bool:
    """Check if a directory is a photree album.

    A directory is an album if it contains a ``.photree/`` directory
    **and** at least one media source (iOS or plain).
    """
    return (directory / PHOTREE_DIR).is_dir() and bool(
        discover_media_sources(directory)
    )


def discover_albums(base_dir: Path) -> list[Path]:
    """Recursively discover album directories under *base_dir*.

    A directory is considered an album when it contains:
    1. A ``.photree/`` directory (album marker), **and**
    2. At least one media source (``ios-{name}/`` or ``{name}-img/``/``{name}-vid/``)

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


def discover_media_sources(album_dir: Path) -> list[MediaSource]:
    """Discover all media sources in an album.

    Scans for:
    1. iOS media sources: ``ios-{name}/`` with ``orig-img/`` or ``orig-vid/``
    2. Plain media sources: ``{name}-img/`` or ``{name}-vid/`` without
       a corresponding ``ios-{name}/`` directory

    Returns media sources sorted with ``main`` first, then alphabetically.
    """
    if not album_dir.is_dir():
        return []

    # 1. Find iOS media sources
    ios_names: set[str] = set()
    ios_sources: list[MediaSource] = []
    for d in album_dir.iterdir():
        if (
            d.is_dir()
            and d.name.startswith(IOS_DIR_PREFIX)
            and ((d / "orig-img").is_dir() or (d / "orig-vid").is_dir())
        ):
            name = d.name.removeprefix(IOS_DIR_PREFIX)
            ios_names.add(name)
            ios_sources.append(ios_media_source(name))

    # 2. Find plain media sources from {name}-img or {name}-vid dirs
    plain_names: set[str] = set()
    for d in album_dir.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            pass
        elif (
            d.name.endswith("-img")
            or d.name.endswith("-vid")
            or d.name.endswith("-jpg")
        ):
            name = d.name.removesuffix("-img").removesuffix("-vid").removesuffix("-jpg")
            if name and name not in ios_names and name not in plain_names:
                plain_names.add(name)

    plain_sources = [plain_media_source(name) for name in plain_names]

    return sorted(
        [*ios_sources, *plain_sources],
        key=lambda ms: (ms.name != DEFAULT_MEDIA_SOURCE, ms.name),
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


def find_files_by_number(
    numbers: set[str],
    directory: Path,
) -> list[str]:
    """Find all files in *directory* whose image number is in *numbers*."""
    return sorted(f for f in list_files(directory) if img_number(f) in numbers)


def find_files_by_stem(
    stems: set[str],
    directory: Path,
) -> list[str]:
    """Find all files in *directory* whose stem (name without extension) is in *stems*."""
    return sorted(f for f in list_files(directory) if Path(f).stem in stems)


_console = Console(highlight=False)


def move_files(
    src_dir: Path,
    dst_dir: Path,
    filenames: list[str],
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> None:
    """Move *filenames* from *src_dir* to *dst_dir*, creating *dst_dir* if needed."""
    if not filenames:
        return
    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)
    for f in filenames:
        src = src_dir / f
        dst = dst_dir / f
        if not dry_run:
            shutil.move(str(src), str(dst))
        if log_cwd is not None:
            _console.print(
                f"{CHECK} {'[dry-run] ' if dry_run else ''}move"
                f" {display_path(src, log_cwd)} → {display_path(dst, log_cwd)}"
            )


def delete_files(
    directory: Path,
    filenames: list[str],
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> int:
    """Delete *filenames* from *directory*. Returns the number of files deleted."""
    for f in filenames:
        path = directory / f
        if not dry_run:
            path.unlink()
        if log_cwd is not None:
            _console.print(
                f"{CHECK} {'[dry-run] ' if dry_run else ''}delete"
                f" {display_path(path, log_cwd)}"
            )
    return len(filenames)
