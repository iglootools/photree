"""
Move and remove media files across album media source directories.

Given relative file paths (as reported by ``album check``), resolves all
associated variants by key (image number for iOS, filename stem for std)
and moves or deletes them.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from photree.album.store.file_matching import find_files_by_key
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
        subdir: str | None = None,
        conflicts: tuple[str, ...] = (),
    ) -> None:
        """Build the error from its *kind*, the album and the fields it reports."""
        self.kind = kind
        self.album_dir = album_dir
        self.rel_path = rel_path
        self.subdir = subdir
        self.conflicts = conflicts
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


def resolve_variants(
    album_dir: Path,
    relative_paths: list[str],
) -> list[tuple[str, list[str]]]:
    """
    Return ``[(subdir, [filename, ...])]`` with every variant file of the paths.

    Searches across the media source directory structure.

    Raises :class:`MediaOpError` when a path cannot be mapped to a media
    source.
    """
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        raise MediaOpError(MediaOpErrorKind.NO_MEDIA_SOURCES, album_dir=album_dir)

    dir_to_ms = _build_dir_to_media_source(media_sources)
    targets = [_locate(album_dir, rel_path, dir_to_ms) for rel_path in relative_paths]
    # Group keys by (media source, image-or-video); dict.fromkeys keeps the
    # first-seen order of the groups.
    groups = dict.fromkeys((t.ms, t.is_video) for t in targets)

    return [
        (subdir, files)
        for ms, video in groups
        for subdir in (ms.video_variant_dirs if video else ms.image_variant_dirs)
        if (
            files := _find_matching_files(
                album_dir,
                subdir,
                {t.key for t in targets if t.ms == ms and t.is_video == video},
                ms,
            )
        )
    ]


def _remove_empty_dirs(
    album_dir: Path,
    subdirs: list[str],
    *,
    dry_run: bool,
) -> None:
    for subdir in subdirs:
        directory = album_dir / subdir
        if directory.is_dir() and not any(directory.iterdir()) and not dry_run:
            directory.rmdir()
            # Also remove parent if it's a nested archive dir (e.g. ios-main/orig-img)
            parent = directory.parent
            if parent != album_dir and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()


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


def move_media(
    source_album: Path,
    dest_album: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
) -> MediaOpResult:
    """
    Move media files and all their variants to another media source.

    Raises :class:`MediaOpError` (``MOVE_CONFLICT``, with the conflicting
    paths) before moving anything if the destination already holds files
    with the same key.
    """
    variants = resolve_variants(source_album, relative_paths)

    dest_dir_to_ms = _build_dir_to_media_source(discover_media_sources(dest_album))
    conflicts = _check_move_conflicts(variants, dest_album, dest_dir_to_ms)
    if conflicts:
        raise MediaOpError(
            MediaOpErrorKind.MOVE_CONFLICT,
            album_dir=dest_album,
            conflicts=tuple(conflicts),
        )

    for subdir, files in variants:
        move_files(source_album / subdir, dest_album / subdir, files, dry_run=dry_run)

    _remove_empty_dirs(
        source_album,
        [subdir for subdir, _ in variants],
        dry_run=dry_run,
    )
    return MediaOpResult(files_by_dir=_files_by_dir(variants))


def rm_media(
    album_dir: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
) -> MediaOpResult:
    """
    Delete the files at *relative_paths* and every variant of them.

    Directories left empty are removed too. Raises :class:`MediaOpError`,
    before deleting anything, when a path cannot be mapped to a media source.
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
