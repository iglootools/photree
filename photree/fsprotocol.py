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
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ---------------------------------------------------------------------------
# Pydantic base model (kebab-case YAML aliases, frozen)
# ---------------------------------------------------------------------------


def _to_kebab(name: str) -> str:
    return name.replace("_", "-")


class PhotreeModel(BaseModel):
    """Base for photree's YAML metadata models: frozen, kebab-case keys."""

    model_config = ConfigDict(
        alias_generator=_to_kebab,
        populate_by_name=True,
        frozen=True,
    )


# ---------------------------------------------------------------------------
# Metadata errors and YAML I/O
#
# Every ``.photree/*.yaml`` store distinguishes *absent* (``None``: nothing
# has been written yet) from *present but unreadable* (an error). Folding the
# two together is how a truncated ``album.yaml`` used to make ``album init``
# mint a fresh ID and silently orphan every collection reference to the old
# one.
# ---------------------------------------------------------------------------


class InvalidMetadataError(ValueError):
    """A metadata file exists but its content cannot be used.

    Carries the path and reason as structured data so the CLI can render the
    path with ``display_path`` and tests can assert on fields, not prose.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid metadata in {path}: {reason}")


def load_yaml_mapping(path: Path) -> dict[str, object] | None:
    """Read a YAML mapping, or ``None`` if *path* does not exist.

    Raises :class:`InvalidMetadataError` when the file exists but is not
    parseable YAML or does not hold a mapping (empty and truncated files
    included).
    """
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InvalidMetadataError(path, f"not valid YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise InvalidMetadataError(
            path, f"expected a YAML mapping, got {type(raw).__name__}"
        )
    return raw


def validate_metadata[M: BaseModel](path: Path, model_cls: type[M], raw: object) -> M:
    """Validate *raw* against *model_cls*, reporting failures against *path*."""
    try:
        return model_cls.model_validate(raw)
    except ValidationError as exc:
        raise InvalidMetadataError(path, str(exc)) from exc


def write_yaml(path: Path, data: object) -> None:
    """Write *data* as block-style YAML in UTF-8, preserving key order."""
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PHOTREE_DIR = ".photree"
ALBUMS_DIR = "albums"
COLLECTIONS_DIR = "collections"
BROWSABLE_DIR = "browsable"


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

    BROWSABLE_JPG = "browsable-jpg"
    BROWSABLE = "browsable"
    ALL = "all"
    ARCHIVE = "archive"


class ShareDirectoryLayout(StrEnum):
    """How albums are organized within the share directory."""

    FLAT = "flat"
    ALBUMS = "albums"
    BY_MONTH = "by-month"


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


class GalleryMetadata(PhotreeModel):
    """Gallery-wide metadata stored in ``.photree/gallery.yaml``."""

    link_mode: LinkMode = Field(
        default=LinkMode.HARDLINK,
        description="Default link mode for refresh and other link-mode operations.",
    )
    faces_enabled: bool = Field(
        default=True,
        description="Enable face detection and clustering during gallery refresh.",
    )
    face_cluster_threshold: float | None = Field(
        default=None,
        description=(
            "Cosine distance threshold for face clustering (0.0-1.0). "
            "Lower = stricter (fewer merges). Default: 0.45 when not set."
        ),
    )


def save_gallery_metadata(gallery_dir: Path, metadata: GalleryMetadata) -> None:
    """Write :class:`GalleryMetadata` to ``.photree/gallery.yaml``."""
    photree_dir = gallery_dir / PHOTREE_DIR
    photree_dir.mkdir(exist_ok=True)
    write_yaml(
        photree_dir / GALLERY_YAML, metadata.model_dump(by_alias=True, mode="json")
    )


def load_gallery_metadata(gallery_yaml_path: Path) -> GalleryMetadata:
    """Read a ``gallery.yaml`` file and return :class:`GalleryMetadata`.

    Raises :class:`InvalidMetadataError` if the file is missing or malformed:
    callers reach this only after resolution found the file, so absence here
    is as much a corruption as bad content.
    """
    raw = load_yaml_mapping(gallery_yaml_path)
    if raw is None:
        raise InvalidMetadataError(gallery_yaml_path, "file not found")
    return validate_metadata(gallery_yaml_path, GalleryMetadata, raw)


class GalleryNotFoundError(ValueError):
    """No ``.photree/gallery.yaml`` was found.

    ``explicit`` is the ``--gallery-dir`` that was given (``None`` when the
    search walked up from ``searched_from``). The message stays free of CLI
    advice and absolute-path formatting: the CLI layer renders both.
    """

    def __init__(self, *, explicit: Path | None, searched_from: Path) -> None:
        self.explicit = explicit
        self.searched_from = searched_from
        super().__init__(
            f"No gallery metadata found at {explicit / PHOTREE_DIR / GALLERY_YAML}"
            if explicit is not None
            else f"No gallery metadata ({PHOTREE_DIR}/{GALLERY_YAML}) found in "
            f"{searched_from} or its parent directories"
        )


def resolve_gallery_dir(
    explicit: Path | None, *, start_dir: Path | None = None
) -> Path:
    """Resolve the gallery root directory.

    Resolution order: explicit path > walk up from *start_dir* (or cwd)
    looking for ``.photree/gallery.yaml``.

    Raises :class:`GalleryNotFoundError` if no gallery metadata is found.
    """
    current = (start_dir or Path.cwd()).resolve()
    if explicit is not None:
        if not (explicit / PHOTREE_DIR / GALLERY_YAML).is_file():
            raise GalleryNotFoundError(explicit=explicit, searched_from=current)
        return explicit

    try:
        return next(
            d
            for d in (current, *current.parents)
            if (d / PHOTREE_DIR / GALLERY_YAML).is_file()
        )
    except StopIteration:
        raise GalleryNotFoundError(explicit=None, searched_from=current) from None


def resolve_gallery_metadata(start_dir: Path) -> GalleryMetadata | None:
    """Walk up from *start_dir* looking for ``.photree/gallery.yaml``.

    Returns the first :class:`GalleryMetadata` found, or ``None``.
    """
    try:
        gallery_dir = resolve_gallery_dir(None, start_dir=start_dir)
    except GalleryNotFoundError:
        return None
    return load_gallery_metadata(gallery_dir / PHOTREE_DIR / GALLERY_YAML)


def resolve_link_mode(explicit: LinkMode | None, start_dir: Path) -> LinkMode:
    """Resolve link mode: explicit CLI arg > gallery.yaml > hardcoded default."""
    if explicit is not None:
        return explicit
    gallery = resolve_gallery_metadata(start_dir)
    return gallery.link_mode if gallery else LinkMode.HARDLINK
