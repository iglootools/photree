"""Export of many albums at once, isolating per-album failures."""

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from photree.album.exporter.single import compute_target_dir, export_album
from photree.album.store.album_discovery import AlbumSelectionError, discover_albums
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


class ExportFailure(NamedTuple):
    """An album whose export failed, with the reason."""

    album_dir: Path
    reason: str


@dataclass(frozen=True)
class BatchExportResult:
    """The counts of a batch export: albums exported and the failures."""

    exported: int = 0
    failed: tuple[ExportFailure, ...] = ()


def find_export_dirs(base_dir: Path) -> list[Path]:
    """
    Return the directories to export under *base_dir*.

    Photree albums (recursively, via ``discover_albums``) plus
    immediate subdirectories that are not already covered — i.e. plain
    directories without ``.photree/album.yaml`` that can be exported as-is.
    """
    photree_albums = set(discover_albums(base_dir))
    # Parents of photree albums should not be treated as plain directories
    photree_parents = {a.parent for a in photree_albums}

    other_dirs = sorted(
        p
        for p in base_dir.iterdir()
        if p.is_dir() and p not in photree_albums and p not in photree_parents
    )

    return sorted([*photree_albums, *other_dirs])


@dataclass(frozen=True)
class _ExportOptions:
    share_dir: Path
    share_layout: ShareDirectoryLayout
    album_layout: AlbumShareLayout
    link_mode: LinkMode


def _resolve_albums(
    base_dir: Path | None,
    album_dirs: Sequence[Path] | None,
) -> list[Path]:
    match (base_dir, album_dirs):
        case (Path() as base, None):
            return find_export_dirs(base)
        case (None, [*dirs]):
            return dirs
        case _:
            raise AlbumSelectionError(("base_dir", "album_dirs"))


def _export_one(
    album_dir: Path,
    options: _ExportOptions,
    *,
    on_exporting: Callable[[str], None] | None,
    on_exported: Callable[[str], None] | None,
    on_error: Callable[[str, str], None] | None,
) -> ExportFailure | None:
    album_name = album_dir.name
    if on_exporting:
        on_exporting(album_name)
    try:
        target_dir = compute_target_dir(
            options.share_dir,
            album_name,
            options.share_layout,
        )
        export_album(
            album_dir,
            target_dir,
            album_layout=options.album_layout,
            link_mode=options.link_mode,
        )
    # A per-album filesystem failure, or a name the share layout cannot place
    # (ValueError from the date parsing), is reported and the batch carries
    # on. Anything else is a bug and propagates.
    except (OSError, ValueError, shutil.Error) as exc:
        if on_error:
            on_error(album_name, str(exc))
        return ExportFailure(album_dir, str(exc))
    else:
        if on_exported:
            on_exported(album_name)
        return None


def run_batch_export(
    *,
    base_dir: Path | None = None,
    album_dirs: Sequence[Path] | None = None,
    share_dir: Path,
    share_layout: ShareDirectoryLayout = ShareDirectoryLayout.FLAT,
    album_layout: AlbumShareLayout = AlbumShareLayout.BROWSABLE_JPG,
    link_mode: LinkMode = LinkMode.HARDLINK,
    on_exporting: Callable[[str], None] | None = None,
    on_exported: Callable[[str], None] | None = None,
    on_error: Callable[[str, str], None] | None = None,
) -> BatchExportResult:
    """
    Export each album, isolating per-album failures.

    Provide exactly one of *base_dir* (discover albums) or *album_dirs*
    (explicit list).

    Callbacks are optional hooks for the CLI layer:

    - ``on_exporting(album_name)`` — called before exporting
    - ``on_exported(album_name)`` — called after success
    - ``on_error(album_name, message)`` — called on failure
    """
    albums = _resolve_albums(base_dir, album_dirs)
    options = _ExportOptions(share_dir, share_layout, album_layout, link_mode)
    outcomes = [
        _export_one(
            album_dir,
            options,
            on_exporting=on_exporting,
            on_exported=on_exported,
            on_error=on_error,
        )
        for album_dir in albums
    ]
    failures = tuple(f for f in outcomes if f is not None)
    return BatchExportResult(exported=len(outcomes) - len(failures), failed=failures)
