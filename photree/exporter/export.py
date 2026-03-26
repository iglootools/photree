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
    AlbumShareLayout,
    Contributor,
    IMG_EXTENSIONS,
    LinkMode,
    VID_EXTENSIONS,
    ShareDirectoryLayout,
    discover_contributors,
    parse_album_year,
)


def _main_dirs(contrib: Contributor) -> tuple[tuple[str, str], ...]:
    """Browsable directories and their export names for a contributor."""
    return (
        (contrib.img_dir, contrib.img_dir),
        (contrib.jpg_dir, contrib.jpg_dir),
        (contrib.vid_dir, contrib.vid_dir),
    )


def _main_jpg_dirs(contrib: Contributor) -> tuple[tuple[str, str], ...]:
    """JPEG + video directories for main-jpg-only export."""
    return (
        (contrib.jpg_dir, contrib.jpg_dir),
        (contrib.vid_dir, contrib.vid_dir),
    )


def _full_copy_dirs(contrib: Contributor) -> tuple[str, ...]:
    """Directories copied as-is in full/full-managed modes."""
    return (
        contrib.orig_img_dir,
        contrib.orig_vid_dir,
        contrib.edit_img_dir,
        contrib.edit_vid_dir,
        contrib.jpg_dir,
    )


def _all_managed_subdirs(contributors: list[Contributor]) -> frozenset[str]:
    """All managed subdirectory names across contributors."""
    return frozenset(
        subdir for c in contributors for subdir in (*c.all_subdirs, c.ios_dir)
    )


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
    """Export browsable dirs for all contributors."""
    target_dir.mkdir(parents=True, exist_ok=True)
    return sum(
        _copy_dir(album_dir / src_name, target_dir / dst_name)
        for contrib in discover_contributors(album_dir)
        for src_name, dst_name in _main_dirs(contrib)
    )


def _export_ios_main_jpg_only(album_dir: Path, target_dir: Path) -> int:
    """Export JPEG + video dirs for all contributors."""
    target_dir.mkdir(parents=True, exist_ok=True)
    return sum(
        _copy_dir(album_dir / src_name, target_dir / dst_name)
        for contrib in discover_contributors(album_dir)
        for src_name, dst_name in _main_jpg_dirs(contrib)
    )


def _export_ios_full_managed(
    album_dir: Path,
    target_dir: Path,
    *,
    link_mode: LinkMode,
) -> int:
    """Export archival + JPEG dirs, then recreate browsable dirs for all contributors."""
    target_dir.mkdir(parents=True, exist_ok=True)
    contributors = discover_contributors(album_dir)

    copied = sum(
        _copy_dir(album_dir / d, target_dir / d)
        for contrib in contributors
        for d in _full_copy_dirs(contrib)
        if (album_dir / d).is_dir()
    )

    # Only rebuild browsable dirs for iOS contributors (they have archival sources).
    # Plain contributors' browsable dirs are already copied as-is above.
    for contrib in (c for c in contributors if c.is_ios):
        heic_result = refresh_main_dir(
            target_dir / contrib.orig_img_dir,
            target_dir / contrib.edit_img_dir,
            target_dir / contrib.img_dir,
            media_extensions=IMG_EXTENSIONS,
            link_mode=link_mode,
        )
        mov_result = refresh_main_dir(
            target_dir / contrib.orig_vid_dir,
            target_dir / contrib.edit_vid_dir,
            target_dir / contrib.vid_dir,
            media_extensions=VID_EXTENSIONS,
            link_mode=link_mode,
        )
        copied += heic_result.copied + mov_result.copied

    return copied


def _export_ios_full(
    album_dir: Path,
    target_dir: Path,
    *,
    link_mode: LinkMode,
) -> int:
    """Export full-managed content plus unmanaged files and directories."""
    copied = _export_ios_full_managed(album_dir, target_dir, link_mode=link_mode)

    managed = _all_managed_subdirs(discover_contributors(album_dir))
    for entry in sorted(os.listdir(album_dir)):
        if entry.startswith(".") or entry in managed:
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
