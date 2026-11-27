"""Export of many albums at once, isolating per-album failures."""

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from photree.album.exporter.single import compute_target_dir, export_album
from photree.album.store.album_discovery import AlbumSelectionError, discover_albums
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


@dataclass(frozen=True)
class ExportFailure:
    """
    An album whose export failed, and why.

    *reason* is the message of the error that stopped the export. When the
    album was refused because other albums of the batch export to the same
    *target_dir*, *reason* is empty and *colliding_albums* names them.
    """

    album_dir: Path
    reason: str = ""
    target_dir: Path | None = None
    colliding_albums: tuple[Path, ...] = ()


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
    dry_run: bool


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
    on_error: Callable[[str, ExportFailure], None] | None,
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
            dry_run=options.dry_run,
        )
    # A per-album filesystem failure, or a name the share layout cannot place
    # (ValueError from the date parsing), is reported and the batch carries
    # on. Anything else is a bug and propagates.
    except (OSError, ValueError, shutil.Error) as exc:
        failure = ExportFailure(album_dir, str(exc))
        if on_error:
            on_error(album_name, failure)
        return failure
    else:
        if on_exported:
            on_exported(album_name)
        return None


def _target_key(
    album_dir: Path,
    share_dir: Path,
    share_layout: ShareDirectoryLayout,
) -> tuple[Path, str] | None:
    """
    Return *album_dir*'s target and the key it collides on, ``None`` if unplaceable.

    The key ignores case: macOS volumes are case-insensitive by default, so
    ``Misc`` and ``misc`` are one directory there.
    """
    try:
        target = compute_target_dir(share_dir, album_dir.name, share_layout)
    except ValueError:
        # Reported by the album's own export, which raises the same error.
        return None
    return target, str(target).casefold()


def find_target_collisions(
    albums: Sequence[Path],
    share_dir: Path,
    share_layout: ShareDirectoryLayout,
) -> dict[Path, ExportFailure]:
    """
    Return a failure for each album that shares its target with another one.

    Exporting either would remove the other's files as stale, so neither is
    exported: the albums must be renamed, or exported to different shares.
    """
    targets = {
        album: placed
        for album in dict.fromkeys(albums)
        if (placed := _target_key(album, share_dir, share_layout)) is not None
    }
    by_key = {
        key: tuple(album for album, (_, k) in targets.items() if k == key)
        for _, key in targets.values()
    }
    return {
        album: ExportFailure(
            album,
            target_dir=target,
            colliding_albums=tuple(a for a in by_key[key] if a != album),
        )
        for album, (target, key) in targets.items()
        if len(by_key[key]) > 1
    }


def _refuse_collision(
    failure: ExportFailure,
    *,
    on_exporting: Callable[[str], None] | None,
    on_error: Callable[[str, ExportFailure], None] | None,
) -> ExportFailure:
    album_name = failure.album_dir.name
    if on_exporting:
        on_exporting(album_name)
    if on_error:
        on_error(album_name, failure)
    return failure


def run_batch_export(
    *,
    base_dir: Path | None = None,
    album_dirs: Sequence[Path] | None = None,
    share_dir: Path,
    share_layout: ShareDirectoryLayout = ShareDirectoryLayout.FLAT,
    album_layout: AlbumShareLayout = AlbumShareLayout.BROWSABLE_JPG,
    link_mode: LinkMode = LinkMode.HARDLINK,
    dry_run: bool = False,
    on_exporting: Callable[[str], None] | None = None,
    on_exported: Callable[[str], None] | None = None,
    on_error: Callable[[str, ExportFailure], None] | None = None,
) -> BatchExportResult:
    """
    Export each album, isolating per-album failures.

    Provide exactly one of *base_dir* (discover albums) or *album_dirs*
    (explicit list). A dry run writes nothing; it still reports the albums
    that would fail, such as a name the share layout cannot place.

    Albums that would export to the same target directory fail without
    being exported (see :func:`find_target_collisions`).

    Callbacks are optional hooks for the CLI layer:

    - ``on_exporting(album_name)`` — called before exporting
    - ``on_exported(album_name)`` — called after success
    - ``on_error(album_name, failure)`` — called on failure
    """
    albums = _resolve_albums(base_dir, album_dirs)
    options = _ExportOptions(
        share_dir,
        share_layout,
        album_layout,
        link_mode,
        dry_run,
    )
    collisions = find_target_collisions(albums, share_dir, share_layout)
    outcomes = [
        _refuse_collision(
            collisions[album_dir],
            on_exporting=on_exporting,
            on_error=on_error,
        )
        if album_dir in collisions
        else _export_one(
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
