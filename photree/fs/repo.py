"""Repository layer — metadata I/O, gallery resolution, album discovery, and file mutations."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import yaml
from rich.console import Console

from ..uiconventions import CHECK
from .fileutils import display_path
from .protocol import (
    ALBUM_YAML,
    DEFAULT_MEDIA_SOURCE,
    GALLERY_YAML,
    IOS_DIR_PREFIX,
    AlbumMetadata,
    GalleryMetadata,
    LinkMode,
    MediaSource,
    PHOTREE_DIR,
    ios_media_source,
    plain_media_source,
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


def save_gallery_metadata(gallery_dir: Path, metadata: GalleryMetadata) -> None:
    """Write :class:`GalleryMetadata` to ``.photree/gallery.yaml``."""
    photree_dir = gallery_dir / PHOTREE_DIR
    photree_dir.mkdir(exist_ok=True)
    path = photree_dir / GALLERY_YAML
    path.write_text(
        yaml.safe_dump(
            metadata.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
    )


def load_gallery_metadata(gallery_yaml_path: Path) -> GalleryMetadata:
    """Read a ``gallery.yaml`` file and return :class:`GalleryMetadata`."""
    with open(gallery_yaml_path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Expected YAML mapping in {gallery_yaml_path}")
    return GalleryMetadata.model_validate(raw)


# ---------------------------------------------------------------------------
# Gallery resolution
# ---------------------------------------------------------------------------


def resolve_gallery_dir(
    explicit: Path | None, *, start_dir: Path | None = None
) -> Path:
    """Resolve the gallery root directory.

    Resolution order: explicit path > walk up from *start_dir* (or cwd)
    looking for ``.photree/gallery.yaml``.

    Raises :class:`ValueError` if no gallery metadata is found.
    """
    if explicit is not None:
        if not (explicit / PHOTREE_DIR / GALLERY_YAML).is_file():
            raise ValueError(
                f"No gallery metadata found at {explicit / PHOTREE_DIR / GALLERY_YAML}.\n"
                "Run 'photree gallery init' to initialize the gallery."
            )
        return explicit

    current = (start_dir or Path.cwd()).resolve()
    while True:
        candidate = current / PHOTREE_DIR / GALLERY_YAML
        if candidate.is_file():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    raise ValueError(
        "No gallery metadata (.photree/gallery.yaml) found in parent directories.\n"
        "Run 'photree gallery init' in the gallery root, or use --gallery-dir."
    )


def resolve_gallery_metadata(start_dir: Path) -> GalleryMetadata | None:
    """Walk up from *start_dir* looking for ``.photree/gallery.yaml``.

    Returns the first :class:`GalleryMetadata` found, or ``None``.
    """
    try:
        gallery_dir = resolve_gallery_dir(None, start_dir=start_dir)
    except ValueError:
        return None
    return load_gallery_metadata(gallery_dir / PHOTREE_DIR / GALLERY_YAML)


def resolve_link_mode(explicit: LinkMode | None, start_dir: Path) -> LinkMode:
    """Resolve link mode: explicit CLI arg > gallery.yaml > hardcoded default."""
    if explicit is not None:
        return explicit
    gallery = resolve_gallery_metadata(start_dir)
    return gallery.link_mode if gallery is not None else LinkMode.HARDLINK


# ---------------------------------------------------------------------------
# Album discovery
# ---------------------------------------------------------------------------


def is_album(directory: Path) -> bool:
    """Check if a directory is a photree album.

    A directory is an album if it contains ``.photree/album.yaml``
    **and** at least one media source (iOS or plain).
    """
    return (directory / PHOTREE_DIR / ALBUM_YAML).is_file() and bool(
        discover_media_sources(directory)
    )


def is_legacy_album(directory: Path) -> bool:
    """Check if a directory has ``.photree/`` but no ``album.yaml`` (needs migration)."""
    return (
        (directory / PHOTREE_DIR).is_dir()
        and not (directory / PHOTREE_DIR / ALBUM_YAML).is_file()
        and bool(discover_media_sources(directory))
    )


def _discover_albums_with(
    base_dir: Path, predicate: Callable[[Path], bool]
) -> list[Path]:
    """Walk *base_dir* collecting directories that satisfy *predicate*.

    The *base_dir* itself is never returned.
    """
    albums: list[Path] = []

    def walk(directory: Path) -> None:
        if predicate(directory):
            albums.append(directory)
            return

        subdirs = sorted(
            child
            for child in directory.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )

        for subdir in subdirs:
            walk(subdir)

    walk(base_dir)
    return albums


def discover_albums(base_dir: Path) -> list[Path]:
    """Recursively discover album directories under *base_dir*.

    A directory is considered an album when it contains:
    1. A ``.photree/album.yaml`` file (album metadata), **and**
    2. At least one media source (``ios-{name}/`` or ``{name}-img/``/``{name}-vid/``)

    The *base_dir* itself is never returned as an album.
    """
    return _discover_albums_with(base_dir, is_album)


def discover_all_albums(base_dir: Path) -> list[Path]:
    """Discover albums including legacy ones (for migration commands).

    Returns directories that are either proper albums (with ``album.yaml``)
    or legacy albums (with ``.photree/`` but no ``album.yaml``).
    """
    return _discover_albums_with(base_dir, lambda d: is_album(d) or is_legacy_album(d))


def discover_media_sources(album_dir: Path) -> list[MediaSource]:
    """Discover all media sources in an album.

    Scans for:
    1. iOS media sources: ``ios-{name}/`` with ``orig-img/`` or ``orig-vid/``
    2. Plain media sources: ``{name}-img/`` or ``{name}-vid/`` without
       a corresponding ``ios-{name}/`` directory

    Returns media sources sorted with ``main`` first, then alphabetically.
    """
    if not album_dir.is_dir():
        return []

    # 1. Find iOS media sources
    ios_names: set[str] = set()
    ios_sources: list[MediaSource] = []
    for d in album_dir.iterdir():
        if (
            d.is_dir()
            and d.name.startswith(IOS_DIR_PREFIX)
            and ((d / "orig-img").is_dir() or (d / "orig-vid").is_dir())
        ):
            name = d.name.removeprefix(IOS_DIR_PREFIX)
            ios_names.add(name)
            ios_sources.append(ios_media_source(name))

    # 2. Find plain media sources from {name}-img or {name}-vid dirs
    plain_names: set[str] = set()
    for d in album_dir.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            pass
        elif (
            d.name.endswith("-img")
            or d.name.endswith("-vid")
            or d.name.endswith("-jpg")
        ):
            name = d.name.removesuffix("-img").removesuffix("-vid").removesuffix("-jpg")
            if name and name not in ios_names and name not in plain_names:
                plain_names.add(name)

    plain_sources = [plain_media_source(name) for name in plain_names]

    return sorted(
        [*ios_sources, *plain_sources],
        key=lambda ms: (ms.name != DEFAULT_MEDIA_SOURCE, ms.name),
    )


# ---------------------------------------------------------------------------
# File mutations
# ---------------------------------------------------------------------------

_console = Console(highlight=False)


def move_files(
    src_dir: Path,
    dst_dir: Path,
    filenames: list[str],
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> None:
    """Move *filenames* from *src_dir* to *dst_dir*, creating *dst_dir* if needed."""
    if not filenames:
        return
    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)
    for f in filenames:
        src = src_dir / f
        dst = dst_dir / f
        if not dry_run:
            shutil.move(str(src), str(dst))
        if log_cwd is not None:
            _console.print(
                f"{CHECK} {'[dry-run] ' if dry_run else ''}move"
                f" {display_path(src, log_cwd)} → {display_path(dst, log_cwd)}"
            )


def delete_files(
    directory: Path,
    filenames: list[str],
    *,
    dry_run: bool,
    log_cwd: Path | None,
) -> int:
    """Delete *filenames* from *directory*. Returns the number of files deleted."""
    for f in filenames:
        path = directory / f
        if not dry_run:
            path.unlink()
        if log_cwd is not None:
            _console.print(
                f"{CHECK} {'[dry-run] ' if dry_run else ''}delete"
                f" {display_path(path, log_cwd)}"
            )
    return len(filenames)
