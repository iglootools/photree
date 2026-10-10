"""Media source discovery — detect iOS and std media sources in an album."""

from __future__ import annotations

from pathlib import Path

from ..formats import IMG_EXTENSIONS, VID_EXTENSIONS
from .media_source import (
    DEFAULT_MEDIA_SOURCE,
    IOS_DIR_PREFIX,
    STD_DIR_PREFIX,
    MediaSource,
    ios_media_source,
    std_media_source,
)


def _is_archive_dir(d: Path, prefix: str) -> bool:
    return (
        d.is_dir()
        and d.name.startswith(prefix)
        and ((d / "orig-img").is_dir() or (d / "orig-vid").is_dir())
    )


def _is_ios_source_dir(d: Path) -> bool:
    return _is_archive_dir(d, IOS_DIR_PREFIX)


def _is_std_source_dir(d: Path) -> bool:
    return _is_archive_dir(d, STD_DIR_PREFIX)


class MediaSourceConflictError(ValueError):
    """An album holds both ``ios-<name>/`` and ``std-<name>/`` for some names.

    Both archives would map to the same browsable directories (``<name>-img/``,
    ``<name>-jpg/``, ``<name>-vid/``) and the same ``media-ids/<name>.yaml``,
    so every derived-data operation would silently clobber one source with the
    other. Carries the album and the conflicting names as data; the CLI renders
    the message.
    """

    def __init__(self, album_dir: Path, names: tuple[str, ...]) -> None:
        self.album_dir = album_dir
        self.names = names
        super().__init__(
            f"Album {album_dir.name!r} has both an iOS and a std archive for "
            f"media source(s): {', '.join(names)}"
        )


def _archive_names(album_dir: Path) -> tuple[frozenset[str], frozenset[str]]:
    """Return ``(ios_names, std_names)`` of the archives found in *album_dir*."""
    if not album_dir.is_dir():
        return frozenset(), frozenset()
    subdirs = [d for d in album_dir.iterdir() if d.is_dir()]
    return (
        frozenset(
            d.name.removeprefix(IOS_DIR_PREFIX)
            for d in subdirs
            if _is_ios_source_dir(d)
        ),
        frozenset(
            d.name.removeprefix(STD_DIR_PREFIX)
            for d in subdirs
            if _is_std_source_dir(d)
        ),
    )


def find_media_source_conflicts(album_dir: Path) -> tuple[str, ...]:
    """Return media source names backed by both an iOS and a std archive.

    Non-raising counterpart of :func:`discover_media_sources`, for checks that
    report the conflict instead of aborting on it.
    """
    ios_names, std_names = _archive_names(album_dir)
    return tuple(sorted(ios_names & std_names))


def has_any_media_source(album_dir: Path) -> bool:
    """Return whether *album_dir* holds at least one media source archive.

    Does not raise on iOS/std name conflicts, so album *discovery* still finds
    a conflicted album and the command operating on it reports the problem.
    """
    ios_names, std_names = _archive_names(album_dir)
    return bool(ios_names or std_names)


def discover_media_sources(album_dir: Path) -> list[MediaSource]:
    """Discover all media sources in an album.

    Scans for:
    1. iOS media sources: ``ios-{name}/`` with ``orig-img/`` or ``orig-vid/``
    2. Std media sources: ``std-{name}/`` with ``orig-img/`` or ``orig-vid/``

    Every media source is backed by an archive directory on disk; browsable
    directories without a backing archive are not media sources.

    Returns media sources sorted with ``main`` first, then alphabetically.

    Raises :class:`MediaSourceConflictError` when a name is backed by both an
    iOS and a std archive.
    """
    ios_names, std_names = _archive_names(album_dir)
    conflicts = tuple(sorted(ios_names & std_names))
    if conflicts:
        raise MediaSourceConflictError(album_dir, conflicts)

    sources = [
        *(ios_media_source(n) for n in ios_names),
        *(std_media_source(n) for n in std_names),
    ]
    return sorted(sources, key=lambda ms: (ms.name != DEFAULT_MEDIA_SOURCE, ms.name))


_MEDIA_EXTENSIONS = IMG_EXTENSIONS | VID_EXTENSIONS


def discover_browsable_media_files(album_dir: Path) -> list[Path]:
    """Collect all media files from an album's browsable directories.

    Searches all media sources' ``{name}-jpg/`` and ``{name}-vid/``
    directories. Falls back to recursive search from the album root
    when no media sources are found.
    """
    media_sources = discover_media_sources(album_dir)
    search_dirs = (
        [
            album_dir / d
            for ms in media_sources
            for d in (ms.jpg_dir, ms.vid_dir)
            if (album_dir / d).is_dir()
        ]
        if media_sources
        else [album_dir]
    )

    return [
        f
        for search_dir in search_dirs
        for f in search_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in _MEDIA_EXTENSIONS
    ]
