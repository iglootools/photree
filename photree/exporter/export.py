"""Export albums to a shared directory.

Supports three album layouts for iOS albums:

- **combined-only**: Copies main-* directories, stripping the ``main-``
  prefix (e.g. ``main-img/`` becomes ``img/``).
- **full-managed**: Copies orig-*, edit-*, and main-jpg directories
  as-is, then recreates main-img and main-vid using the specified
  link mode.
- **full**: Same as full-managed, plus copies any unmanaged files and
  directories from the album.

Non-iOS albums are copied in their entirety regardless of album layout.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..album.combined import refresh_main_dir
from ..album.preflight import AlbumType, detect_album_type
from ..fsprotocol import (
    MAIN_IMG_DIR,
    MAIN_JPG_DIR,
    MAIN_VID_DIR,
    IMG_EXTENSIONS,
    IOS_ALBUM_SUBDIRS,
    AlbumShareLayout,
    LinkMode,
    MOV_EXTENSIONS,
    ORIG_IMG_DIR,
    ORIG_VID_DIR,
    EDIT_IMG_DIR,
    EDIT_VID_DIR,
    ShareDirectoryLayout,
    parse_album_year,
)


# main-* dirs and the name they get after stripping the prefix
_MAIN_DIRS = (
    (MAIN_IMG_DIR, "img"),
    (MAIN_JPG_DIR, "jpg"),
    (MAIN_VID_DIR, "vid"),
)

# Same as _MAIN_DIRS but without main-img (for main-jpg-only export)
_MAIN_JPG_DIRS = (
    (MAIN_JPG_DIR, "jpg"),
    (MAIN_VID_DIR, "vid"),
)

# Directories copied as-is in full/full-managed modes
_FULL_COPY_DIRS = (
    ORIG_IMG_DIR,
    ORIG_VID_DIR,
    EDIT_IMG_DIR,
    EDIT_VID_DIR,
    MAIN_JPG_DIR,
)

_IOS_ALBUM_SUBDIRS_SET = frozenset(IOS_ALBUM_SUBDIRS)


@dataclass(frozen=True)
class ExportResult:
    """Result of exporting a single album."""

    album_name: str
    album_type: AlbumType
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


def _copytree(src: Path, dst: Path) -> int:
    """Recursively copy a directory tree. Returns the number of files copied."""
    if not src.is_dir():
        return 0

    shutil.copytree(src, dst, dirs_exist_ok=True)
    return sum(1 for _ in dst.rglob("*") if _.is_file())


def _export_other(album_dir: Path, target_dir: Path) -> int:
    """Export a non-iOS album by copying everything."""
    return _copytree(album_dir, target_dir)


def _export_ios_main_only(album_dir: Path, target_dir: Path) -> int:
    """Export main-* dirs with the ``main-`` prefix stripped."""
    target_dir.mkdir(parents=True, exist_ok=True)
    return sum(
        _copy_dir(album_dir / src_name, target_dir / dst_name)
        for src_name, dst_name in _MAIN_DIRS
    )


def _export_ios_main_jpg_only(album_dir: Path, target_dir: Path) -> int:
    """Export main-jpg and main-vid (no main-img) with the ``main-`` prefix stripped."""
    target_dir.mkdir(parents=True, exist_ok=True)
    return sum(
        _copy_dir(album_dir / src_name, target_dir / dst_name)
        for src_name, dst_name in _MAIN_JPG_DIRS
    )


def _export_ios_full_managed(
    album_dir: Path,
    target_dir: Path,
    *,
    link_mode: LinkMode,
) -> int:
    """Export orig/edit/main-jpg, then recreate main-img and main-vid."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy managed dirs that exist
    copied = sum(
        _copy_dir(album_dir / d, target_dir / d)
        for d in _FULL_COPY_DIRS
        if (album_dir / d).is_dir()
    )

    # Recreate main-img and main-vid from the target's orig/edit
    heic_result = refresh_main_dir(
        target_dir / ORIG_IMG_DIR,
        target_dir / EDIT_IMG_DIR,
        target_dir / MAIN_IMG_DIR,
        media_extensions=IMG_EXTENSIONS,
        link_mode=link_mode,
    )
    mov_result = refresh_main_dir(
        target_dir / ORIG_VID_DIR,
        target_dir / EDIT_VID_DIR,
        target_dir / MAIN_VID_DIR,
        media_extensions=MOV_EXTENSIONS,
        link_mode=link_mode,
    )

    return copied + heic_result.copied + mov_result.copied


def _export_ios_full(
    album_dir: Path,
    target_dir: Path,
    *,
    link_mode: LinkMode,
) -> int:
    """Export full-managed content plus unmanaged files and directories."""
    copied = _export_ios_full_managed(album_dir, target_dir, link_mode=link_mode)

    # Copy unmanaged entries (files and directories not in IOS_ALBUM_SUBDIRS)
    for entry in sorted(os.listdir(album_dir)):
        if entry.startswith(".") or entry in _IOS_ALBUM_SUBDIRS_SET:
            continue
        src_path = album_dir / entry
        dst_path = target_dir / entry
        if src_path.is_file():
            shutil.copy2(src_path, dst_path)
            copied += 1
        elif src_path.is_dir():
            copied += _copytree(src_path, dst_path)

    return copied


def export_album(
    album_dir: Path,
    target_dir: Path,
    *,
    album_layout: AlbumShareLayout = AlbumShareLayout.MAIN_ONLY,
    link_mode: LinkMode = LinkMode.HARDLINK,
) -> ExportResult:
    """Export a single album to *target_dir*.

    The caller is responsible for computing *target_dir* (e.g. via
    :func:`compute_target_dir`).

    For non-iOS albums, all files are copied regardless of *album_layout*.
    For iOS albums, the export behaviour depends on *album_layout*.
    """
    album_name = album_dir.name
    album_type = detect_album_type(album_dir)

    match album_type:
        case AlbumType.OTHER:
            files_copied = _export_other(album_dir, target_dir)
        case AlbumType.IOS:
            match album_layout:
                case AlbumShareLayout.MAIN_ONLY:
                    files_copied = _export_ios_main_only(album_dir, target_dir)
                case AlbumShareLayout.MAIN_JPG_ONLY:
                    files_copied = _export_ios_main_jpg_only(album_dir, target_dir)
                case AlbumShareLayout.FULL_MANAGED:
                    files_copied = _export_ios_full_managed(
                        album_dir, target_dir, link_mode=link_mode
                    )
                case AlbumShareLayout.FULL:
                    files_copied = _export_ios_full(
                        album_dir, target_dir, link_mode=link_mode
                    )

    return ExportResult(
        album_name=album_name,
        album_type=album_type,
        files_copied=files_copied,
    )
