"""
Move and remove media files across album media source directories.

Given relative file paths (as reported by ``album check``), resolves all
associated variants by key (image number for iOS, filename stem for std)
and moves or deletes them. A move carries the media IDs of the moved keys
along, so collections that reference them still resolve.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.store.file_matching import find_files_by_key
from photree.album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    load_media_metadata,
    save_media_metadata,
)
from photree.album.store.media_source import MediaSource
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.common.fs import delete_files, move_files

# A media file sits in a directory: at least the directory and the file name.
_MIN_PATH_PARTS = 2


@dataclass(frozen=True)
class MediaOpResult:
    """The files a media operation moved or removed, as ``(subdir, files)`` pairs."""

    files_by_dir: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def total(self) -> int:
        """Return the number of files moved or removed."""
        return sum(len(files) for _, files in self.files_by_dir)


class MediaOpErrorKind(StrEnum):
    """Why a move/remove request was refused before touching any file."""

    NO_MEDIA_SOURCES = "no-media-sources"
    PATH_WITHOUT_DIRECTORY = "path-without-directory"
    UNKNOWN_DIRECTORY = "unknown-directory"
    MOVE_CONFLICT = "move-conflict"
    MEDIA_SOURCE_TYPE_MISMATCH = "media-source-type-mismatch"
    NO_MATCHING_FILE = "no-matching-file"


class MediaOpError(ValueError):
    """
    A media operation that cannot run.

    Carries structured fields; the CLI renders them with display paths.
    ``ValueError`` subclass for callers that already catch that.
    """

    def __init__(
        self,
        kind: MediaOpErrorKind,
        *,
        album_dir: Path,
        rel_path: str | None = None,
        rel_paths: tuple[str, ...] = (),
        subdir: str | None = None,
        conflicts: tuple[str, ...] = (),
        media_sources: tuple[str, ...] = (),
    ) -> None:
        """Build the error from its *kind*, the album and the fields it reports."""
        self.kind = kind
        self.album_dir = album_dir
        self.rel_path = rel_path
        self.rel_paths = rel_paths
        self.subdir = subdir
        self.conflicts = conflicts
        self.media_sources = media_sources
        super().__init__(f"{kind}: {album_dir.name}")


def _build_dir_to_media_source(
    media_sources: list[MediaSource],
) -> dict[str, MediaSource]:
    return {d: ms for ms in media_sources for d in ms.all_subdirs}


def _find_matching_files(
    album_dir: Path,
    subdir: str,
    keys: set[str],
    ms: MediaSource,
) -> list[str]:
    directory = album_dir / subdir
    if not directory.is_dir():
        return []
    return find_files_by_key(keys, directory, ms.key_fn)


@dataclass(frozen=True)
class _Target:
    """One requested file, located: its media source, kind, and key."""

    ms: MediaSource
    is_video: bool
    key: str


def _locate(
    album_dir: Path,
    rel_path: str,
    dir_to_ms: dict[str, MediaSource],
) -> _Target:
    """
    Locate a file in its media source.

    Handles both flat (``main-jpg/file``) and nested
    (``ios-main/orig-img/file``) directories. The directory, not the file's
    extension, says whether the media is an image or a video: a Live Photo's
    ``.MOV`` sits in the image directories beside its still and belongs to
    that image.
    """
    parts = Path(rel_path).parts
    if len(parts) < _MIN_PATH_PARTS:
        raise MediaOpError(
            MediaOpErrorKind.PATH_WITHOUT_DIRECTORY,
            album_dir=album_dir,
            rel_path=rel_path,
        )
    subdir = str(Path(*parts[:-1]))
    ms = dir_to_ms.get(subdir)
    if ms is None:
        raise MediaOpError(
            MediaOpErrorKind.UNKNOWN_DIRECTORY,
            album_dir=album_dir,
            subdir=subdir,
        )
    filename = parts[-1]
    return _Target(
        ms=ms,
        is_video=subdir in ms.video_variant_dirs,
        key=ms.key_fn(filename),
    )


@dataclass(frozen=True)
class _MediaGroup:
    """The requested media of one media source and kind, with their variant files."""

    ms: MediaSource
    is_video: bool
    variants: tuple[tuple[str, tuple[str, ...]], ...]


def _resolve_groups(album_dir: Path, relative_paths: list[str]) -> list[_MediaGroup]:
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        raise MediaOpError(MediaOpErrorKind.NO_MEDIA_SOURCES, album_dir=album_dir)

    dir_to_ms = _build_dir_to_media_source(media_sources)
    targets = [_locate(album_dir, rel_path, dir_to_ms) for rel_path in relative_paths]
    # Group keys by (media source, image-or-video); dict.fromkeys keeps the
    # first-seen order of the groups.
    groups = dict.fromkeys((t.ms, t.is_video) for t in targets)

    resolved = [
        _MediaGroup(
            ms=ms,
            is_video=video,
            variants=tuple(
                (subdir, tuple(files))
                for subdir in (
                    ms.video_variant_dirs if video else ms.image_variant_dirs
                )
                if (
                    files := _find_matching_files(
                        album_dir,
                        subdir,
                        {t.key for t in targets if t.ms == ms and t.is_video == video},
                        ms,
                    )
                )
            ),
        )
        for ms, video in groups
    ]
    _require_every_path_matched(album_dir, relative_paths, targets, resolved)
    return resolved


def _require_every_path_matched(
    album_dir: Path,
    relative_paths: list[str],
    targets: list[_Target],
    groups: list[_MediaGroup],
) -> None:
    """Raise ``NO_MATCHING_FILE`` with every path whose key matches no file."""
    found = {
        (g.ms, g.is_video, g.ms.key_fn(f))
        for g in groups
        for _, files in g.variants
        for f in files
    }
    unmatched = tuple(
        rel_path
        for rel_path, t in zip(relative_paths, targets, strict=True)
        if (t.ms, t.is_video, t.key) not in found
    )
    if unmatched:
        raise MediaOpError(
            MediaOpErrorKind.NO_MATCHING_FILE,
            album_dir=album_dir,
            rel_paths=unmatched,
        )


def _variants_of(groups: list[_MediaGroup]) -> list[tuple[str, list[str]]]:
    return [(subdir, list(files)) for g in groups for subdir, files in g.variants]


def resolve_variants(
    album_dir: Path,
    relative_paths: list[str],
) -> list[tuple[str, list[str]]]:
    """
    Return ``[(subdir, [filename, ...])]`` with every variant file of the paths.

    Searches across the media source directory structure.

    Raises :class:`MediaOpError` when a path cannot be mapped to a media
    source, or names a file that matches nothing (``NO_MATCHING_FILE``, with
    every such path).
    """
    return _variants_of(_resolve_groups(album_dir, relative_paths))


def _rmdir_if_empty(directory: Path) -> bool:
    """Remove *directory* when it exists and is empty; return whether it did."""
    is_empty = directory.is_dir() and not any(directory.iterdir())
    if is_empty:
        directory.rmdir()
    return is_empty


def _remove_empty_dirs(
    album_dir: Path,
    subdirs: list[str],
    *,
    dry_run: bool,
) -> None:
    """Remove each emptied subdir, and the archive dir holding it once empty too."""
    for directory in (album_dir / subdir for subdir in subdirs):
        if not dry_run and _rmdir_if_empty(directory) and directory.parent != album_dir:
            _rmdir_if_empty(directory.parent)


def _check_move_conflicts(
    variants: list[tuple[str, list[str]]],
    dest_album: Path,
    dest_dir_to_ms: dict[str, MediaSource],
) -> list[str]:
    """Return a sorted list of conflicting file paths, empty if no conflicts."""
    return sorted(
        {
            f"{subdir}/{existing}"
            for subdir, files in variants
            if (ms := dest_dir_to_ms.get(subdir)) is not None
            for existing in _find_matching_files(
                dest_album,
                subdir,
                {ms.key_fn(f) for f in files},
                ms,
            )
        },
    )


def _find_media_source_type_mismatches(
    groups: list[_MediaGroup],
    dest_media_sources: list[MediaSource],
) -> tuple[str, ...]:
    """Return the moved media sources' names the destination has with the other type."""
    dest_types = {ms.name: ms.media_source_type for ms in dest_media_sources}
    return tuple(
        sorted(
            {
                g.ms.name
                for g in groups
                if dest_types.get(g.ms.name, g.ms.media_source_type)
                != g.ms.media_source_type
            },
        ),
    )


def _validate_move(groups: list[_MediaGroup], dest_album: Path) -> None:
    dest_media_sources = discover_media_sources(dest_album)
    mismatches = _find_media_source_type_mismatches(groups, dest_media_sources)
    if mismatches:
        raise MediaOpError(
            MediaOpErrorKind.MEDIA_SOURCE_TYPE_MISMATCH,
            album_dir=dest_album,
            media_sources=mismatches,
        )

    conflicts = _check_move_conflicts(
        _variants_of(groups),
        dest_album,
        _build_dir_to_media_source(dest_media_sources),
    )
    if conflicts:
        raise MediaOpError(
            MediaOpErrorKind.MOVE_CONFLICT,
            album_dir=dest_album,
            conflicts=tuple(conflicts),
        )


def _moved_keys(groups: list[_MediaGroup]) -> dict[tuple[str, bool], frozenset[str]]:
    return {
        (g.ms.name, g.is_video): frozenset(
            g.ms.key_fn(f) for _, files in g.variants for f in files
        )
        for g in groups
    }


def _without_keys(ids: dict[str, str], keys: frozenset[str]) -> dict[str, str]:
    return {uuid: key for uuid, key in ids.items() if key not in keys}


def _with_keys(ids: dict[str, str], keys: frozenset[str]) -> dict[str, str]:
    return {uuid: key for uuid, key in ids.items() if key in keys}


def _transfer_ids(
    source_ms: MediaSourceMediaMetadata,
    dest_ms: MediaSourceMediaMetadata,
    image_keys: frozenset[str],
    video_keys: frozenset[str],
) -> tuple[MediaSourceMediaMetadata, MediaSourceMediaMetadata]:
    return (
        MediaSourceMediaMetadata(
            images=_without_keys(source_ms.images, image_keys),
            videos=_without_keys(source_ms.videos, video_keys),
        ),
        MediaSourceMediaMetadata(
            images={
                **_without_keys(dest_ms.images, image_keys),
                **_with_keys(source_ms.images, image_keys),
            },
            videos={
                **_without_keys(dest_ms.videos, video_keys),
                **_with_keys(source_ms.videos, video_keys),
            },
        ),
    )


def compute_media_id_transfer(
    source: MediaMetadata,
    dest: MediaMetadata,
    moved_keys: dict[tuple[str, bool], frozenset[str]],
) -> tuple[MediaMetadata, MediaMetadata]:
    """
    Return the source's and destination's media IDs after a move.

    *moved_keys* holds the keys moved, by ``(media source name, is_video)``.
    Each moved key's UUID leaves the source and joins the same media source
    and kind in the destination. A destination entry for a moved key is
    dropped: no file with that key was there (the move refuses conflicts), so
    the entry was stale, and keeping it would give the moved media two IDs.
    """
    empty = MediaSourceMediaMetadata()
    transfers = {
        name: _transfer_ids(
            source.media_sources.get(name, empty),
            dest.media_sources.get(name, empty),
            moved_keys.get((name, False), frozenset()),
            moved_keys.get((name, True), frozenset()),
        )
        for name in sorted({name for name, _ in moved_keys})
    }
    return (
        MediaMetadata(
            media_sources={
                **source.media_sources,
                **{
                    n: s for n, (s, _) in transfers.items() if n in source.media_sources
                },
            },
        ),
        MediaMetadata(
            media_sources={
                **dest.media_sources,
                **{
                    n: d
                    for n, (_, d) in transfers.items()
                    if n in dest.media_sources or d.images or d.videos
                },
            },
        ),
    )


def move_media(
    source_album: Path,
    dest_album: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
) -> MediaOpResult:
    """
    Move media files and all their variants to another media source.

    Raises :class:`MediaOpError` before moving anything:

    - ``NO_MATCHING_FILE``, with the paths, when a path matches no file.
    - ``MEDIA_SOURCE_TYPE_MISMATCH``, with the media source names, when the
      destination has a media source of the same name but the other type
      (iOS or std): moving would put an ``ios-<name>/`` and a
      ``std-<name>/`` archive side by side, which every derived-data command
      then refuses.
    - ``MOVE_CONFLICT``, with the conflicting paths, when the destination
      already holds files with the same key.

    Raises :class:`~photree.foundation.metadata_io.InvalidMetadataError`,
    also before moving anything, when either album's media IDs cannot be
    read: moving without them would let the next refresh mint new IDs.
    """
    groups = _resolve_groups(source_album, relative_paths)
    variants = _variants_of(groups)
    _validate_move(groups, dest_album)
    source_ids = load_media_metadata(source_album)
    dest_ids = load_media_metadata(dest_album)

    for subdir, files in variants:
        move_files(source_album / subdir, dest_album / subdir, files, dry_run=dry_run)
    if not dry_run:
        _save_transferred_media_ids(
            source_album,
            dest_album,
            source_ids,
            dest_ids,
            _moved_keys(groups),
        )

    _remove_empty_dirs(
        source_album,
        [subdir for subdir, _ in variants],
        dry_run=dry_run,
    )
    return MediaOpResult(files_by_dir=_files_by_dir(variants))


def _save_transferred_media_ids(
    source_album: Path,
    dest_album: Path,
    source_ids: MediaMetadata | None,
    dest_ids: MediaMetadata | None,
    moved_keys: dict[tuple[str, bool], frozenset[str]],
) -> None:
    """Write the media IDs after the move, leaving untouched any that did not change."""
    source_before = source_ids or MediaMetadata()
    dest_before = dest_ids or MediaMetadata()
    source_after, dest_after = compute_media_id_transfer(
        source_before,
        dest_before,
        moved_keys,
    )
    if source_after != source_before:
        save_media_metadata(source_album, source_after)
    if dest_after != dest_before:
        save_media_metadata(dest_album, dest_after)


def rm_media(
    album_dir: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
) -> MediaOpResult:
    """
    Delete the files at *relative_paths* and every variant of them.

    Directories left empty are removed too. Raises :class:`MediaOpError`,
    before deleting anything, when a path cannot be mapped to a media source
    or matches no file.
    """
    variants = resolve_variants(album_dir, relative_paths)

    for subdir, files in variants:
        delete_files(album_dir / subdir, files, dry_run=dry_run)

    _remove_empty_dirs(album_dir, [subdir for subdir, _ in variants], dry_run=dry_run)
    return MediaOpResult(files_by_dir=_files_by_dir(variants))


def _files_by_dir(
    variants: list[tuple[str, list[str]]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((subdir, tuple(files)) for subdir, files in variants)
