"""Album persistence — metadata I/O, album discovery, and media source detection."""

from __future__ import annotations

from pathlib import Path

import yaml

from ...common.fs import matching_subdirectories
from ...fsprotocol import PHOTREE_DIR
from .protocol import (
    ALBUM_YAML,
    DEFAULT_MEDIA_SOURCE,
    IMG_EXTENSIONS,
    IOS_DIR_PREFIX,
    STD_DIR_PREFIX,
    VID_EXTENSIONS,
    AlbumMetadata,
    MediaSource,
    ios_media_source,
    std_media_source,
)

# ---------------------------------------------------------------------------
# Metadata I/O
# ---------------------------------------------------------------------------


def load_album_metadata(album_dir: Path) -> AlbumMetadata | None:
    """Read ``.photree/album.yaml``, or ``None`` if missing."""
    path = album_dir / PHOTREE_DIR / ALBUM_YAML
    if not path.is_file():
        return None
    with open(path) as f:
        raw = yaml.safe_load(f)
    return AlbumMetadata.model_validate(raw) if isinstance(raw, dict) else None


def save_album_metadata(album_dir: Path, metadata: AlbumMetadata) -> None:
    """Write :class:`AlbumMetadata` to ``.photree/album.yaml``."""
    photree_dir = album_dir / PHOTREE_DIR
    photree_dir.mkdir(exist_ok=True)
    path = photree_dir / ALBUM_YAML
    path.write_text(
        yaml.safe_dump(
            metadata.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
    )


# ---------------------------------------------------------------------------
# Album discovery
# ---------------------------------------------------------------------------


def is_album(directory: Path) -> bool:
    """Check if a directory is a photree album.

    A directory is an album if it contains ``.photree/album.yaml``
    **and** at least one media source (iOS or std).
    """
    return (directory / PHOTREE_DIR / ALBUM_YAML).is_file() and bool(
        discover_media_sources(directory)
    )


def has_media_sources(directory: Path) -> bool:
    """Check if a directory has at least one media source.

    Unlike :func:`is_album`, this does **not** require ``.photree/album.yaml``.
    """
    return bool(discover_media_sources(directory))


def discover_albums(base_dir: Path) -> list[Path]:
    """Recursively discover album directories under *base_dir*.

    A directory is considered an album when it contains:
    1. A ``.photree/album.yaml`` file (album metadata), **and**
    2. At least one media source (``ios-{name}/`` or ``{name}-img/``/``{name}-vid/``)

    The *base_dir* itself is never returned as an album.
    """
    return matching_subdirectories(base_dir, is_album)


def discover_potential_albums(base_dir: Path) -> list[Path]:
    """Recursively discover directories with media sources under *base_dir*.

    Unlike :func:`discover_albums`, this does **not** require
    ``.photree/album.yaml`` — it finds any directory with at least one
    media source. Useful for ``init`` commands that create ``album.yaml``.

    The *base_dir* itself is never returned.
    """
    return matching_subdirectories(base_dir, has_media_sources)


# ---------------------------------------------------------------------------
# Media source discovery
# ---------------------------------------------------------------------------


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
