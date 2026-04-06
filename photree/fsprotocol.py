"""Shared filesystem protocol — foundational types used across domains.

This module contains types and functions shared by both the album and
gallery domains.  Gallery-specific definitions (metadata model, I/O,
resolution) live here rather than in the gallery package to avoid a
circular dependency: album CLI commands need ``resolve_link_mode``,
but the gallery package imports from album.  Placing them in this
shared foundation module breaks the cycle.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Pydantic base model (kebab-case YAML aliases, frozen)
# ---------------------------------------------------------------------------


def _to_kebab(name: str) -> str:
    return name.replace("_", "-")


class _BaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_kebab,
        populate_by_name=True,
        frozen=True,
    )


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PHOTREE_DIR = ".photree"
ALBUMS_DIR = "albums"
COLLECTIONS_DIR = "collections"


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class LinkMode(StrEnum):
    """How main-dir files reference their source."""

    COPY = "copy"
    HARDLINK = "hardlink"
    SYMLINK = "symlink"


# ---------------------------------------------------------------------------
# Export layout enums
#
# These describe how albums are organized within a share directory.
# They live here (rather than in album.exporter) so that clihelpers
# and config can reference them without depending on the album package.
# ---------------------------------------------------------------------------

SHARE_SENTINEL = ".photree-share"


class AlbumShareLayout(StrEnum):
    """How an album is exported."""

    MAIN_JPG = "main-jpg"
    MAIN = "main"
    ALL = "all"


class ShareDirectoryLayout(StrEnum):
    """How albums are organized within the share directory."""

    FLAT = "flat"
    ALBUMS = "albums"


# ---------------------------------------------------------------------------
# Gallery metadata and resolution
#
# These gallery-specific types and functions live here (rather than in
# the gallery package) to avoid a circular dependency: album CLI
# commands need resolve_link_mode, but the gallery package imports
# from album.  Placing them in this shared foundation module breaks
# the cycle.
# ---------------------------------------------------------------------------

GALLERY_YAML = "gallery.yaml"


class GalleryMetadata(_BaseModel):
    """Gallery-wide metadata stored in ``.photree/gallery.yaml``."""

    link_mode: LinkMode = Field(
        default=LinkMode.HARDLINK,
        description="Default link mode for optimize and other link-mode operations.",
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
    try:
        return next(
            d
            for d in (current, *current.parents)
            if (d / PHOTREE_DIR / GALLERY_YAML).is_file()
        )
    except StopIteration:
        raise ValueError(
            "No gallery metadata (.photree/gallery.yaml) found in parent directories.\n"
            "Run 'photree gallery init' in the gallery root, or use --gallery-dir."
        ) from None


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
    return gallery.link_mode if gallery else LinkMode.HARDLINK
