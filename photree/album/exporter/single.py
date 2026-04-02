"""Export albums to a shared directory.

Supports three album layouts for albums with archives (iOS and std sources):

- **main-jpg** (default): Copies main-jpg/ and main-vid/ (most compatible formats).
- **main**: Copies main-img/, main-jpg/, and main-vid/.
- **all**: Copies archival directories (orig-*, edit-*) and main-jpg/ as-is,
  then recreates main-img/ and main-vid/ using the specified link mode.

Albums without archives (legacy std sources with browsable dirs only)
are copied in their entirety regardless of album layout.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ...fsprotocol import PHOTREE_DIR, LinkMode
from ..browsable import refresh_browsable_dir
from ..exporter.protocol import AlbumShareLayout, ShareDirectoryLayout
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import (
    IMG_EXTENSIONS,
    VID_EXTENSIONS,
    MediaSource,
    parse_album_year,
)


def _main_jpg_dirs(ms: MediaSource) -> tuple[tuple[str, str], ...]:
    """JPEG + video directories for the ``main-jpg`` layout."""
    return (
        (ms.jpg_dir, ms.jpg_dir),
        (ms.vid_dir, ms.vid_dir),
    )


def _main_dirs(ms: MediaSource) -> tuple[tuple[str, str], ...]:
    """Browsable directories and their export names for a media source."""
    return (
        (ms.img_dir, ms.img_dir),
        (ms.jpg_dir, ms.jpg_dir),
        (ms.vid_dir, ms.vid_dir),
    )


def _full_copy_dirs(ms: MediaSource) -> tuple[str, ...]:
    """Archival + JPEG directories copied as-is in the ``all`` layout.

    Works for any media source with archives (iOS or std).
    """
    return (
        ms.orig_img_dir,
        ms.orig_vid_dir,
        ms.edit_img_dir,
        ms.edit_vid_dir,
        ms.jpg_dir,
    )


@dataclass(frozen=True)
class ExportResult:
    """Result of exporting a single album."""

    album_name: str
    album_type: str
    files_copied: int


def compute_target_dir(
    share_dir: Path,
    album_name: str,
    share_layout: ShareDirectoryLayout,
) -> Path:
    """Compute the export target directory for an album."""
    match share_layout:
        case ShareDirectoryLayout.FLAT:
            return share_dir / album_name
        case ShareDirectoryLayout.ALBUMS:
            year = parse_album_year(album_name)
            return share_dir / year / album_name


def _copy_dir(src: Path, dst: Path) -> int:
    """Copy all files from *src* to *dst*, creating *dst* if needed.

    Returns the number of files copied.
    """
    if not src.is_dir():
        return 0

    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for entry in sorted(os.listdir(src)):
        src_path = src / entry
        if src_path.is_file():
            shutil.copy2(src_path, dst / entry)
            count += 1
    return count


def _is_dotfile(name: str) -> bool:
    """Check if a filename is a dotfile (starts with ``'.'``)."""
    return name.startswith(".")


def _ignore_dotfiles(_directory: str, contents: list[str]) -> set[str]:
    """``shutil.copytree`` ignore function that skips dotfiles."""
    return {name for name in contents if _is_dotfile(name)}


def _copytree(src: Path, dst: Path) -> int:
    """Recursively copy a directory tree, skipping dotfiles.

    Returns the number of files copied.
    """
    if not src.is_dir():
        return 0

    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore_dotfiles)
    return sum(1 for _ in dst.rglob("*") if _.is_file())


def _export_plain(album_dir: Path, target_dir: Path) -> int:
    """Export an album without archives by copying everything."""
    return _copytree(album_dir, target_dir)


def _export_main_jpg(album_dir: Path, target_dir: Path) -> int:
    """Export JPEG + video dirs for all media sources."""
    target_dir.mkdir(parents=True, exist_ok=True)
    return sum(
        _copy_dir(album_dir / src_name, target_dir / dst_name)
        for ms in discover_media_sources(album_dir)
        for src_name, dst_name in _main_jpg_dirs(ms)
    )


def _export_main(album_dir: Path, target_dir: Path) -> int:
    """Export browsable dirs for all media sources."""
    target_dir.mkdir(parents=True, exist_ok=True)
    return sum(
        _copy_dir(album_dir / src_name, target_dir / dst_name)
        for ms in discover_media_sources(album_dir)
        for src_name, dst_name in _main_dirs(ms)
    )


def _export_all(
    album_dir: Path,
    target_dir: Path,
    *,
    link_mode: LinkMode,
) -> int:
    """Export archival + JPEG dirs, then recreate browsable dirs for all media sources."""
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / PHOTREE_DIR).mkdir(exist_ok=True)
    media_sources = discover_media_sources(album_dir)

    copied = sum(
        _copy_dir(album_dir / d, target_dir / d)
        for ms in media_sources
        for d in _full_copy_dirs(ms)
        if (album_dir / d).is_dir()
    )

    # Rebuild browsable dirs for media sources whose archive dir exists on disk.
    # Legacy std sources without archives have their browsable dirs already
    # copied as-is above (via jpg_dir in _full_copy_dirs).
    for ms in (m for m in media_sources if (album_dir / m.archive_dir).is_dir()):
        heic_result = refresh_browsable_dir(
            target_dir / ms.orig_img_dir,
            target_dir / ms.edit_img_dir,
            target_dir / ms.img_dir,
            media_extensions=IMG_EXTENSIONS,
            key_fn=ms.key_fn,
            link_mode=link_mode,
        )
        mov_result = refresh_browsable_dir(
            target_dir / ms.orig_vid_dir,
            target_dir / ms.edit_vid_dir,
            target_dir / ms.vid_dir,
            media_extensions=VID_EXTENSIONS,
            key_fn=ms.key_fn,
            link_mode=link_mode,
        )
        copied += heic_result.copied + mov_result.copied

    return copied


def _has_archives(album_dir: Path) -> bool:
    """Check whether the album has any media source with an archive directory on disk."""
    return any(
        (album_dir / ms.archive_dir).is_dir()
        for ms in discover_media_sources(album_dir)
    )


def export_album(
    album_dir: Path,
    target_dir: Path,
    *,
    album_layout: AlbumShareLayout = AlbumShareLayout.MAIN_JPG,
    link_mode: LinkMode = LinkMode.HARDLINK,
) -> ExportResult:
    """Export a single album to *target_dir*.

    The caller is responsible for computing *target_dir* (e.g. via
    :func:`compute_target_dir`).

    Albums without archives (legacy std sources with browsable dirs only)
    are copied in their entirety regardless of *album_layout*.
    Albums with archives (iOS or std) are exported according to *album_layout*.
    """
    album_name = album_dir.name
    media_sources = discover_media_sources(album_dir)
    album_type = "ios" if any(ms.is_ios for ms in media_sources) else "std"

    if not _has_archives(album_dir):
        files_copied = _export_plain(album_dir, target_dir)
    else:
        match album_layout:
            case AlbumShareLayout.MAIN_JPG:
                files_copied = _export_main_jpg(album_dir, target_dir)
            case AlbumShareLayout.MAIN:
                files_copied = _export_main(album_dir, target_dir)
            case AlbumShareLayout.ALL:
                files_copied = _export_all(album_dir, target_dir, link_mode=link_mode)

    return ExportResult(
        album_name=album_name,
        album_type=album_type,
        files_copied=files_copied,
    )
