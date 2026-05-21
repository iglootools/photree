"""Media source discovery — detect iOS, std, and legacy media sources in an album."""

from __future__ import annotations

from pathlib import Path

from .protocol import (
    DEFAULT_MEDIA_SOURCE,
    IMG_EXTENSIONS,
    IOS_DIR_PREFIX,
    STD_DIR_PREFIX,
    VID_EXTENSIONS,
    MediaSource,
    ios_media_source,
    std_media_source,
)


def _is_ios_source_dir(d: Path) -> bool:
    return (
        d.is_dir()
        and d.name.startswith(IOS_DIR_PREFIX)
        and ((d / "orig-img").is_dir() or (d / "orig-vid").is_dir())
    )


def _is_std_source_dir(d: Path) -> bool:
    return (
        d.is_dir()
        and d.name.startswith(STD_DIR_PREFIX)
        and ((d / "orig-img").is_dir() or (d / "orig-vid").is_dir())
    )


_BROWSABLE_SUFFIXES = ("-img", "-vid", "-jpg")


def _strip_browsable_suffix(name: str) -> str | None:
    for suffix in _BROWSABLE_SUFFIXES:
        if name.endswith(suffix):
            return name.removesuffix(suffix) or None
    return None


def discover_media_sources(album_dir: Path) -> list[MediaSource]:
    """Discover all media sources in an album.

    Scans for:
    1. iOS media sources: ``ios-{name}/`` with ``orig-img/`` or ``orig-vid/``
    2. Std media sources: ``std-{name}/`` with ``orig-img/`` or ``orig-vid/``
    3. Legacy std media sources: ``{name}-img/`` or ``{name}-vid/`` without
       a corresponding ``ios-{name}/`` or ``std-{name}/`` directory

    Returns media sources sorted with ``main`` first, then alphabetically.
    """
    if not album_dir.is_dir():
        return []

    subdirs = [d for d in album_dir.iterdir() if d.is_dir()]

    # 1. iOS media sources
    ios_names = {
        d.name.removeprefix(IOS_DIR_PREFIX) for d in subdirs if _is_ios_source_dir(d)
    }

    # 2. Std media sources (migrated — have std-{name}/ archive)
    std_names = {
        d.name.removeprefix(STD_DIR_PREFIX) for d in subdirs if _is_std_source_dir(d)
    }

    # 3. Legacy std media sources: browsable dirs not backed by ios-{name}/ or std-{name}/
    legacy_std_names = {
        name
        for d in subdirs
        if not d.name.startswith(".")
        for name in [_strip_browsable_suffix(d.name)]
        if name and name not in ios_names and name not in std_names
    }

    sources = [
        *(ios_media_source(n) for n in ios_names),
        *(std_media_source(n) for n in std_names),
        *(std_media_source(n) for n in legacy_std_names),
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
    if media_sources:
        search_dirs = [
            album_dir / d
            for ms in media_sources
            for d in (ms.jpg_dir, ms.vid_dir)
            if (album_dir / d).is_dir()
        ]
    else:
        search_dirs = [album_dir]

    return [
        f
        for search_dir in search_dirs
        for f in search_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in _MEDIA_EXTENSIONS
    ]
