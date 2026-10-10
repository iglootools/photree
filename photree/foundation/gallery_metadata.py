"""Gallery metadata (``.photree/gallery.yaml``) and gallery resolution.

These gallery-specific types live in the foundation layer rather than in the
gallery package because the album and albums CLIs resolve the gallery's link
mode too, and the gallery package imports from album: placing them here keeps
the package graph acyclic.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from .layout import PHOTREE_DIR
from .linking import LinkMode
from .metadata_io import (
    InvalidMetadataError,
    load_yaml_mapping,
    validate_metadata,
    write_yaml,
)
from .model import PhotreeModel

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
