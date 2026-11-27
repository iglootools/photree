"""
Export albums to a shared directory.

Supports four album layouts for albums with archives (iOS and std sources):

- **browsable-jpg** (default): Copies {name}-jpg/ and {name}-vid/ (most compatible
  formats).
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

import shutil
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.browsable import refresh_browsable_dir
from photree.album.live_photo import (
    augment_browsable_img_with_live_photo_videos,
    compute_live_photo_videos,
)
from photree.album.store.media_source import MediaSource
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.album.store.protocol import CACHE_DIR
from photree.dates import parse_month_prefix, parse_year_prefix
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout

type _IgnoreFn = Callable[[str, list[str]], set[str]]


def _browsable_jpg_dirs(ms: MediaSource) -> tuple[str, ...]:
    return (ms.jpg_dir, ms.vid_dir)


def _browsable_dirs(ms: MediaSource) -> tuple[str, ...]:
    return (ms.img_dir, ms.jpg_dir, ms.vid_dir)


def _archive_dirs(ms: MediaSource) -> tuple[str, ...]:
    return (
        ms.orig_img_dir,
        ms.orig_vid_dir,
        ms.edit_img_dir,
        ms.edit_vid_dir,
    )


def _full_copy_dirs(ms: MediaSource) -> tuple[str, ...]:
    """
    Return the archival and JPEG directories copied as-is in the ``all`` layout.

    Works for any media source with archives (iOS or std).
    """
    return (*_archive_dirs(ms), ms.jpg_dir)


class ExportedAlbumType(StrEnum):
    """What kind of album an export found: iOS, std only, or a plain directory."""

    IOS = "ios"  # at least one iOS media source
    STD = "std"  # only std media sources
    PLAIN = "plain"  # no media source: a plain directory, copied as-is


@dataclass(frozen=True)
class ExportResult:
    """
    The outcome of one album's export: its name, type and file counts.

    *files_removed* counts the stale files an earlier export left behind.
    """

    album_name: str
    album_type: ExportedAlbumType
    files_copied: int
    files_removed: int = 0


def compute_target_dir(
    share_dir: Path,
    album_name: str,
    share_layout: ShareDirectoryLayout,
) -> Path:
    """
    Return the directory *album_name* is exported to under *share_dir*.

    The ``albums`` layout nests it under its year and ``by-month`` under its
    month, both parsed from the name's date prefix; ``flat`` puts it directly
    under *share_dir*. Raises :class:`ValueError` when the layout needs a date
    the name does not start with.
    """
    match share_layout:
        case ShareDirectoryLayout.FLAT:
            return share_dir / album_name
        case ShareDirectoryLayout.ALBUMS:
            year = parse_year_prefix(album_name)
            return share_dir / year / album_name
        case ShareDirectoryLayout.BY_MONTH:
            month = parse_month_prefix(album_name)
            return share_dir / month / album_name


type _Copy = tuple[Path, Path]
"""A file to copy: its source in the album and its destination in the share."""


def _dir_copies(src: Path, dst: Path) -> list[_Copy]:
    """Return the copies of the files directly under *src* (not its subdirs)."""
    if not src.is_dir():
        return []
    else:
        return [
            (src / name, dst / name)
            for name in sorted(e.name for e in src.iterdir() if e.is_file())
        ]


def _dirs_copies(
    album_dir: Path,
    target_dir: Path,
    subdirs: Sequence[str],
) -> list[_Copy]:
    return [c for d in subdirs for c in _dir_copies(album_dir / d, target_dir / d)]


def _is_dotfile(name: str) -> bool:
    return name.startswith(".")


def _ignore_dotfiles(_directory: str, contents: list[str]) -> set[str]:
    return {name for name in contents if _is_dotfile(name)}


def _files_to_copy(src: Path, ignore: _IgnoreFn) -> Iterator[Path]:
    """Yield the files under *src*, recursively, minus what *ignore* drops."""
    names = [p.name for p in src.iterdir()]
    ignored = ignore(str(src), names)
    for name in sorted(set(names) - ignored):
        path = src / name
        if path.is_dir():
            yield from _files_to_copy(path, ignore)
        else:
            yield path


def _tree_copies(
    src: Path,
    dst: Path,
    *,
    ignore: _IgnoreFn = _ignore_dotfiles,
) -> list[_Copy]:
    """Return the copies of every file under *src*, recursively."""
    if not src.is_dir():
        return []
    else:
        return [(f, dst / f.relative_to(src)) for f in _files_to_copy(src, ignore)]


def _metadata_copies(album_dir: Path, target_dir: Path) -> list[_Copy]:
    """
    Return the copies of ``.photree/`` metadata, minus the derived ``cache/``.

    ``album.yaml`` (stable album ID) and ``media-ids/`` (stable image/video
    UUIDs) are preserved; ``cache/`` (EXIF + face data) is omitted because it
    is regenerable via ``albums refresh``.
    """
    return _tree_copies(
        album_dir / PHOTREE_DIR,
        target_dir / PHOTREE_DIR,
        ignore=lambda _directory, _contents: {CACHE_DIR},
    )


def _planned_copies(
    album_dir: Path,
    target_dir: Path,
    media_sources: Sequence[MediaSource],
    album_layout: AlbumShareLayout,
) -> list[_Copy]:
    """Return every file the export copies from *album_dir* into *target_dir*."""
    if not media_sources:
        # No recognizable media-source structure: copy everything, whatever
        # the layout, since we cannot tell source-of-truth from derived data.
        return _tree_copies(album_dir, target_dir)
    else:

        def dirs_copies(
            dirs_of: Callable[[MediaSource], tuple[str, ...]],
        ) -> list[_Copy]:
            return [
                c
                for ms in media_sources
                for c in _dirs_copies(album_dir, target_dir, dirs_of(ms))
            ]

        match album_layout:
            case AlbumShareLayout.ARCHIVE:
                return [
                    *dirs_copies(_archive_dirs),
                    *_metadata_copies(album_dir, target_dir),
                ]
            case AlbumShareLayout.BROWSABLE_JPG:
                return dirs_copies(_browsable_jpg_dirs)
            case AlbumShareLayout.BROWSABLE:
                return dirs_copies(_browsable_dirs)
            case AlbumShareLayout.ALL:
                # The metadata (album ID, media IDs) is what lets the export
                # be refreshed or re-imported as the same album.
                return [
                    *dirs_copies(_full_copy_dirs),
                    *_metadata_copies(album_dir, target_dir),
                ]


def _rebuilt_dirs(
    target_dir: Path,
    media_sources: Sequence[MediaSource],
    album_layout: AlbumShareLayout,
) -> frozenset[Path]:
    """Return the browsable dirs the ``all`` layout recreates from the archive."""
    match album_layout:
        case AlbumShareLayout.ALL:
            return frozenset(
                target_dir / d for ms in media_sources for d in (ms.img_dir, ms.vid_dir)
            )
        case _:
            return frozenset()


def _files_under(directory: Path, skip: frozenset[Path]) -> Iterator[Path]:
    """Yield every file (or link) under *directory*, not descending into *skip*."""
    for entry in sorted(e for e in directory.iterdir() if e not in skip):
        if entry.is_dir() and not entry.is_symlink():
            yield from _files_under(entry, skip)
        else:
            yield entry


def _stale_files(
    target_dir: Path,
    copies: Sequence[_Copy],
    rebuilt_dirs: frozenset[Path],
) -> list[Path]:
    """
    Return the files in *target_dir* this export would not write.

    What an earlier export left there and the album no longer has: media
    removed since, a media source or a directory the layout no longer exports.
    The rebuilt browsable dirs are left out: their rebuild clears them.
    """
    if not target_dir.is_dir():
        return []
    else:
        written = {dst for _, dst in copies}
        return [f for f in _files_under(target_dir, rebuilt_dirs) if f not in written]


def _remove_empty_dirs(directory: Path) -> None:
    """Remove the empty directories under *directory*, deepest first."""
    for entry in directory.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            _remove_empty_dirs(entry)
            if not any(entry.iterdir()):
                entry.rmdir()


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # A link an earlier export left (the ``all`` layout's browsable dirs) is
    # replaced, never written through to the file it points to.
    dst.unlink(missing_ok=True)
    shutil.copy2(src, dst)


def _live_photo_videos(
    archive_dir: Path,
    target_dir: Path,
    ms: MediaSource,
    link_mode: LinkMode,
    *,
    dry_run: bool,
) -> int:
    """
    Place an iOS source's Live Photo videos in ``{name}-img/``, as refresh does.

    A dry run counts them from the archive: the img dir they would go into
    does not exist yet.
    """
    orig, edit = archive_dir / ms.orig_img_dir, archive_dir / ms.edit_img_dir
    if not ms.is_ios:
        return 0
    elif dry_run:
        return len(compute_live_photo_videos(orig, edit, ms.vid_extensions, ms.key_fn))
    else:
        return augment_browsable_img_with_live_photo_videos(
            orig,
            edit,
            target_dir / ms.img_dir,
            vid_extensions=ms.vid_extensions,
            key_fn=ms.key_fn,
            link_mode=link_mode,
            dry_run=False,
        )


def _rebuild_browsable(
    archive_dir: Path,
    target_dir: Path,
    ms: MediaSource,
    link_mode: LinkMode,
    *,
    dry_run: bool,
) -> int:
    """
    Recreate ``{name}-img/`` and ``{name}-vid/`` in *target_dir*, as refresh does.

    From the archive under *archive_dir*: the exported one, or the album's own
    for a dry run, which has not exported it and only counts the files. Like
    refresh, it uses an iOS source's own extensions and places its Live Photo
    videos in ``{name}-img/``, so ``album check`` finds the export fresh.
    """
    img = refresh_browsable_dir(
        archive_dir / ms.orig_img_dir,
        archive_dir / ms.edit_img_dir,
        target_dir / ms.img_dir,
        media_extensions=ms.img_extensions,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    live = _live_photo_videos(
        archive_dir,
        target_dir,
        ms,
        link_mode,
        dry_run=dry_run,
    )
    vid = refresh_browsable_dir(
        archive_dir / ms.orig_vid_dir,
        archive_dir / ms.edit_vid_dir,
        target_dir / ms.vid_dir,
        media_extensions=ms.vid_extensions,
        key_fn=ms.key_fn,
        link_mode=link_mode,
        dry_run=dry_run,
    )
    return img.copied + live + vid.copied


def _album_type(media_sources: Sequence[MediaSource]) -> ExportedAlbumType:
    match media_sources:
        case []:
            return ExportedAlbumType.PLAIN
        case _ if any(ms.is_ios for ms in media_sources):
            return ExportedAlbumType.IOS
        case _:
            return ExportedAlbumType.STD


def export_album(
    album_dir: Path,
    target_dir: Path,
    *,
    album_layout: AlbumShareLayout = AlbumShareLayout.BROWSABLE_JPG,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
) -> ExportResult:
    """
    Export one album into *target_dir*, mirroring it.

    The caller is responsible for computing *target_dir* (e.g. via
    :func:`compute_target_dir`).
    Albums with archives (iOS or std) are exported according to *album_layout*.
    Files an earlier export left in *target_dir* that this one does not write
    are removed, so media deleted from the album since does not survive in
    the share. A dry run writes nothing and returns the same counts.
    """
    media_sources = discover_media_sources(album_dir)
    copies = _planned_copies(album_dir, target_dir, media_sources, album_layout)
    rebuilt_dirs = _rebuilt_dirs(target_dir, media_sources, album_layout)
    stale = _stale_files(target_dir, copies, rebuilt_dirs)
    if not dry_run:
        # Stale files go first: the ``all`` layout rebuilds its browsable dirs
        # from the exported archive, which must no longer hold deleted media.
        for path in stale:
            path.unlink()
        if stale:
            _remove_empty_dirs(target_dir)
        for src, dst in copies:
            _copy_file(src, dst)
    archive_dir = album_dir if dry_run else target_dir
    rebuilt = (
        sum(
            _rebuild_browsable(archive_dir, target_dir, ms, link_mode, dry_run=dry_run)
            for ms in media_sources
        )
        if rebuilt_dirs
        else 0
    )
    return ExportResult(
        album_name=album_dir.name,
        album_type=_album_type(media_sources),
        files_copied=len(copies) + rebuilt,
        files_removed=len(stale),
    )
