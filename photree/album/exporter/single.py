"""Export albums to a shared directory.

Supports four album layouts for albums with archives (iOS and std sources):

- **browsable-jpg** (default): Copies {name}-jpg/ and {name}-vid/ (most compatible formats).
- **browsable**: Copies {name}-img/, {name}-jpg/, and {name}-vid/.
- **all**: Copies archival directories (orig-*, edit-*), {name}-jpg/ and the
  ``.photree/`` metadata (excluding the derived ``cache/``) as-is, then
  recreates {name}-img/ and {name}-vid/ using the specified link mode.
- **archive**: Copies only the archive (orig-*, edit-*) plus ``.photree/``
  metadata (excluding the derived ``cache/``). All browsable/JPEG dirs are
  dropped — they are regenerable via ``albums refresh``. Useful for
  space-efficient backups to destinations without hardlink/symlink support
  (e.g. MEGA).

Directories that contain no recognizable media source are copied in their
entirety regardless of album layout — except the ``archive`` layout, which
copies only the archive dirs and ``.photree/`` metadata.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ...fsprotocol import PHOTREE_DIR, LinkMode
from ..browsable import refresh_browsable_dir
from ..exporter.protocol import AlbumShareLayout, ShareDirectoryLayout
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import (
    CACHE_DIR,
    IMG_EXTENSIONS,
    VID_EXTENSIONS,
    MediaSource,
    parse_album_month,
    parse_album_year,
)

_IgnoreFn = Callable[[str, list[str]], set[str]]


def _browsable_jpg_dirs(ms: MediaSource) -> tuple[str, ...]:
    """JPEG + video directories for the ``browsable-jpg`` layout."""
    return (ms.jpg_dir, ms.vid_dir)


def _browsable_dirs(ms: MediaSource) -> tuple[str, ...]:
    """Browsable directories for the ``browsable`` layout."""
    return (ms.img_dir, ms.jpg_dir, ms.vid_dir)


def _archive_dirs(ms: MediaSource) -> tuple[str, ...]:
    """Archive directories (originals + edits) for the ``archive`` layout."""
    return (
        ms.orig_img_dir,
        ms.orig_vid_dir,
        ms.edit_img_dir,
        ms.edit_vid_dir,
    )


def _full_copy_dirs(ms: MediaSource) -> tuple[str, ...]:
    """Archival + JPEG directories copied as-is in the ``all`` layout.

    Works for any media source with archives (iOS or std).
    """
    return (*_archive_dirs(ms), ms.jpg_dir)


class ExportedAlbumType(StrEnum):
    IOS = "ios"  # at least one iOS media source
    STD = "std"  # only std media sources
    PLAIN = "plain"  # no media source: a plain directory, copied as-is


@dataclass(frozen=True)
class ExportResult:
    """Result of exporting a single album."""

    album_name: str
    album_type: ExportedAlbumType
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
        case ShareDirectoryLayout.BY_MONTH:
            month = parse_album_month(album_name)
            return share_dir / month / album_name


def _copy_dir(src: Path, dst: Path) -> int:
    """Copy the files directly in *src* to *dst*, creating *dst* if needed.

    Returns the number of files copied.
    """
    if not src.is_dir():
        return 0
    else:
        dst.mkdir(parents=True, exist_ok=True)
        files = [e for e in sorted(os.listdir(src)) if (src / e).is_file()]
        for entry in files:
            shutil.copy2(src / entry, dst / entry)
        return len(files)


def _copy_dirs(album_dir: Path, target_dir: Path, subdirs: Sequence[str]) -> int:
    return sum(_copy_dir(album_dir / d, target_dir / d) for d in subdirs)


def _is_dotfile(name: str) -> bool:
    """Check if a filename is a dotfile (starts with ``'.'``)."""
    return name.startswith(".")


def _ignore_dotfiles(_directory: str, contents: list[str]) -> set[str]:
    """``shutil.copytree`` ignore function that skips dotfiles."""
    return {name for name in contents if _is_dotfile(name)}


def _files_to_copy(src: Path, ignore: _IgnoreFn) -> Iterator[Path]:
    """The files ``shutil.copytree(src, ..., ignore=ignore)`` copies."""
    names = os.listdir(src)
    ignored = ignore(str(src), names)
    for name in sorted(set(names) - ignored):
        path = src / name
        if path.is_dir():
            yield from _files_to_copy(path, ignore)
        else:
            yield path


def _copytree(src: Path, dst: Path, *, ignore: _IgnoreFn = _ignore_dotfiles) -> int:
    """Recursively copy a directory tree, skipping dotfiles by default.

    Returns the number of files copied from *src* — not the number of files in
    *dst*, which also counts what a previous export left there.
    """
    if not src.is_dir():
        return 0
    else:
        copied = sum(1 for _ in _files_to_copy(src, ignore))
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)
        return copied


def _export_plain(album_dir: Path, target_dir: Path) -> int:
    """Export an album without archives by copying everything."""
    return _copytree(album_dir, target_dir)


def _export_dirs(
    album_dir: Path,
    target_dir: Path,
    media_sources: Sequence[MediaSource],
    dirs_of: Callable[[MediaSource], tuple[str, ...]],
) -> int:
    """Copy the *dirs_of* each media source."""
    target_dir.mkdir(parents=True, exist_ok=True)
    return sum(_copy_dirs(album_dir, target_dir, dirs_of(ms)) for ms in media_sources)


def _rebuild_browsable(target_dir: Path, ms: MediaSource, link_mode: LinkMode) -> int:
    """Recreate ``{name}-img/`` and ``{name}-vid/`` from the exported archive."""
    img = refresh_browsable_dir(
        target_dir / ms.orig_img_dir,
        target_dir / ms.edit_img_dir,
        target_dir / ms.img_dir,
        media_extensions=IMG_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
    )
    vid = refresh_browsable_dir(
        target_dir / ms.orig_vid_dir,
        target_dir / ms.edit_vid_dir,
        target_dir / ms.vid_dir,
        media_extensions=VID_EXTENSIONS,
        key_fn=ms.key_fn,
        link_mode=link_mode,
    )
    return img.copied + vid.copied


def _copy_photree_metadata(album_dir: Path, target_dir: Path) -> int:
    """Copy ``.photree/`` metadata, excluding the derived ``cache/`` subdir.

    ``album.yaml`` (stable album ID) and ``media-ids/`` (stable image/video
    UUIDs) are preserved; ``cache/`` (EXIF + face data) is omitted because it
    is regenerable via ``albums refresh``. Returns the number of files copied.
    """
    return _copytree(
        album_dir / PHOTREE_DIR,
        target_dir / PHOTREE_DIR,
        ignore=lambda _directory, _contents: {CACHE_DIR},
    )


def _export_all(
    album_dir: Path,
    target_dir: Path,
    media_sources: Sequence[MediaSource],
    *,
    link_mode: LinkMode,
) -> int:
    """Export archive + JPEG dirs and metadata, then rebuild browsable dirs.

    The metadata (album ID, media IDs) is what lets the export be refreshed
    or re-imported as the same album rather than a new one.
    """
    copied = _export_dirs(album_dir, target_dir, media_sources, _full_copy_dirs)
    return (
        copied
        + _copy_photree_metadata(album_dir, target_dir)
        + sum(_rebuild_browsable(target_dir, ms, link_mode) for ms in media_sources)
    )


def _export_archive(
    album_dir: Path, target_dir: Path, media_sources: Sequence[MediaSource]
) -> int:
    """Export only the archive (originals + edits) plus ``.photree/`` metadata.

    Copies each media source's ``orig-*``/``edit-*`` directories. All derived
    dirs (``{name}-jpg/``, ``{name}-img/``, ``{name}-vid/``) are dropped — they
    are regenerable via ``albums refresh``.
    """
    return _export_dirs(
        album_dir, target_dir, media_sources, _archive_dirs
    ) + _copy_photree_metadata(album_dir, target_dir)


def _album_type(media_sources: Sequence[MediaSource]) -> ExportedAlbumType:
    match media_sources:
        case []:
            return ExportedAlbumType.PLAIN
        case _ if any(ms.is_ios for ms in media_sources):
            return ExportedAlbumType.IOS
        case _:
            return ExportedAlbumType.STD


def _export_files(
    album_dir: Path,
    target_dir: Path,
    media_sources: Sequence[MediaSource],
    *,
    album_layout: AlbumShareLayout,
    link_mode: LinkMode,
) -> int:
    if not media_sources:
        # No recognizable media-source structure: copy everything, whatever
        # the layout, since we cannot tell source-of-truth from derived data.
        return _export_plain(album_dir, target_dir)
    else:
        match album_layout:
            case AlbumShareLayout.ARCHIVE:
                return _export_archive(album_dir, target_dir, media_sources)
            case AlbumShareLayout.BROWSABLE_JPG:
                return _export_dirs(
                    album_dir, target_dir, media_sources, _browsable_jpg_dirs
                )
            case AlbumShareLayout.BROWSABLE:
                return _export_dirs(
                    album_dir, target_dir, media_sources, _browsable_dirs
                )
            case AlbumShareLayout.ALL:
                return _export_all(
                    album_dir, target_dir, media_sources, link_mode=link_mode
                )


def export_album(
    album_dir: Path,
    target_dir: Path,
    *,
    album_layout: AlbumShareLayout = AlbumShareLayout.BROWSABLE_JPG,
    link_mode: LinkMode = LinkMode.HARDLINK,
) -> ExportResult:
    """Export a single album to *target_dir*.

    The caller is responsible for computing *target_dir* (e.g. via
    :func:`compute_target_dir`).
    Albums with archives (iOS or std) are exported according to *album_layout*.
    """
    media_sources = discover_media_sources(album_dir)
    return ExportResult(
        album_name=album_dir.name,
        album_type=_album_type(media_sources),
        files_copied=_export_files(
            album_dir,
            target_dir,
            media_sources,
            album_layout=album_layout,
            link_mode=link_mode,
        ),
    )
