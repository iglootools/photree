"""Move and remove media files across album media source directories.

Given relative file paths (as reported by ``album check``), resolves all
associated variants by key (image number for iOS, filename stem for std)
and moves or deletes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..common.formatting import indent
from ..common.fs import delete_files, display_path, file_ext, move_files
from .formats import VID_EXTENSIONS
from .store.file_matching import find_files_by_key
from .store.media_source import MediaSource
from .store.media_sources_discovery import discover_media_sources

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MediaOpResult:
    """Result of a move or remove operation."""

    files_by_dir: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def total(self) -> int:
        return sum(len(files) for _, files in self.files_by_dir)


class MediaOpErrorKind(StrEnum):
    """Why a move/remove request was refused before touching any file."""

    NO_MEDIA_SOURCES = "no-media-sources"
    PATH_WITHOUT_DIRECTORY = "path-without-directory"
    UNKNOWN_DIRECTORY = "unknown-directory"
    MOVE_CONFLICT = "move-conflict"


class MediaOpError(ValueError):
    """A move/remove request that cannot be carried out.

    Carries structured fields; :func:`format_media_op_error` renders them for
    the CLI with display paths. ``ValueError`` subclass for callers that
    already catch that.
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
        self.kind = kind
        self.album_dir = album_dir
        self.rel_path = rel_path
        self.subdir = subdir
        self.conflicts = conflicts
        super().__init__(f"{kind}: {album_dir.name}")


# ---------------------------------------------------------------------------
# Directory-to-media-source mapping
# ---------------------------------------------------------------------------


def _build_dir_to_media_source(
    media_sources: list[MediaSource],
) -> dict[str, MediaSource]:
    """Map every media source subdirectory name to its media source."""
    return {d: ms for ms in media_sources for d in ms.all_subdirs}


# ---------------------------------------------------------------------------
# Variant resolution
# ---------------------------------------------------------------------------


def _is_video(filename: str) -> bool:
    return file_ext(filename) in VID_EXTENSIONS


def _find_matching_files(
    album_dir: Path,
    subdir: str,
    keys: set[str],
    ms: MediaSource,
) -> list[str]:
    """Find files in *album_dir/subdir* matching *keys* using *ms.key_fn*."""
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
    album_dir: Path, rel_path: str, dir_to_ms: dict[str, MediaSource]
) -> _Target:
    """Map a relative path (``main-jpg/IMG_E3219.jpg``) to its media source and key.

    Handles both flat (``main-jpg/file``) and nested
    (``ios-main/orig-img/file``) directories.
    """
    parts = Path(rel_path).parts
    if len(parts) < 2:
        raise MediaOpError(
            MediaOpErrorKind.PATH_WITHOUT_DIRECTORY,
            album_dir=album_dir,
            rel_path=rel_path,
        )
    subdir = str(Path(*parts[:-1]))
    ms = dir_to_ms.get(subdir)
    if ms is None:
        raise MediaOpError(
            MediaOpErrorKind.UNKNOWN_DIRECTORY, album_dir=album_dir, subdir=subdir
        )
    filename = parts[-1]
    return _Target(ms=ms, is_video=_is_video(filename), key=ms.key_fn(filename))


def resolve_variants(
    album_dir: Path,
    relative_paths: list[str],
) -> list[tuple[str, list[str]]]:
    """Resolve all file variants for the given relative paths.

    Returns ``[(subdir, [filename, ...])]`` with all variant files found
    across the media source directory structure.

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


# ---------------------------------------------------------------------------
# Move / Remove
# ---------------------------------------------------------------------------


def _remove_empty_dirs(
    album_dir: Path,
    subdirs: list[str],
    *,
    dry_run: bool,
) -> None:
    """Remove subdirectories that are now empty after a move/rm operation."""
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
    """Check for conflicts in the destination album before moving.

    Returns a sorted list of conflicting file paths, empty if no conflicts.
    """
    return sorted(
        {
            f"{subdir}/{existing}"
            for subdir, files in variants
            if (ms := dest_dir_to_ms.get(subdir)) is not None
            for existing in _find_matching_files(
                dest_album, subdir, {ms.key_fn(f) for f in files}, ms
            )
        }
    )


def move_media(
    source_album: Path,
    dest_album: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
) -> MediaOpResult:
    """Move media files and all their variants from *source_album* to *dest_album*.

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
        source_album, [subdir for subdir, _ in variants], dry_run=dry_run
    )
    return MediaOpResult(files_by_dir=_files_by_dir(variants))


def rm_media(
    album_dir: Path,
    relative_paths: list[str],
    *,
    dry_run: bool = False,
) -> MediaOpResult:
    """Remove media files and all their variants from *album_dir*."""
    variants = resolve_variants(album_dir, relative_paths)

    for subdir, files in variants:
        delete_files(album_dir / subdir, files, dry_run=dry_run)

    _remove_empty_dirs(album_dir, [subdir for subdir, _ in variants], dry_run=dry_run)
    return MediaOpResult(files_by_dir=_files_by_dir(variants))


def _files_by_dir(
    variants: list[tuple[str, list[str]]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((subdir, tuple(files)) for subdir, files in variants)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_MAX_LISTED_CONFLICTS = 10


def format_media_op_error(exc: MediaOpError, cwd: Path) -> str:
    """Render a :class:`MediaOpError` for the CLI, with display paths."""
    album = display_path(exc.album_dir, cwd)
    match exc.kind:
        case MediaOpErrorKind.NO_MEDIA_SOURCES:
            return f"No media sources found in {album}."
        case MediaOpErrorKind.PATH_WITHOUT_DIRECTORY:
            return (
                f'"{exc.rel_path}" must be a relative path with a directory'
                " (e.g. main-jpg/IMG_E3219.jpg)."
            )
        case MediaOpErrorKind.UNKNOWN_DIRECTORY:
            return (
                f'Directory "{exc.subdir}" does not match any media source in {album}.'
            )
        case MediaOpErrorKind.MOVE_CONFLICT:
            return _format_move_conflicts(exc.conflicts, album)


def _format_move_conflicts(conflicts: tuple[str, ...], album: Path) -> str:
    shown = conflicts[:_MAX_LISTED_CONFLICTS]
    hidden = len(conflicts) - len(shown)
    return "\n".join(
        [
            f"Move would conflict with {len(conflicts)} existing file(s) in {album}:",
            *(indent(c) for c in shown),
            *([indent(f"... and {hidden} more")] if hidden > 0 else []),
            "Use a different media source to avoid conflicts.",
        ]
    )


def media_op_summary(
    verb: str,
    files_by_dir: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    total = sum(len(files) for _, files in files_by_dir)
    if total == 0:
        return f"Done. No files to {verb.lower()}."
    parts = ", ".join(f"{len(files)} from {name}" for name, files in files_by_dir)
    return f"Done. {verb} {total} file(s): {parts}."


def media_op_check_suggestions(album_dirs: list[str]) -> str:
    return "\n".join(
        [
            "",
            "Suggested next steps:",
            *(indent(f'photree album check --album-dir "{d}"') for d in album_dirs),
        ]
    )
