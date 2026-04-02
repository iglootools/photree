"""Repository layer — backward-compatible re-export facade.

Canonical locations:
- Album persistence: :mod:`album.store.fs`
- Gallery persistence: :mod:`gallery.store.fs`

Note: Gallery functions are defined here temporarily to avoid circular
imports (fs -> gallery -> album.naming -> fs). They will move to
gallery.store.fs once callers migrate off fs in Phase F.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .protocol import (
    GALLERY_YAML,
    GalleryMetadata,
    LinkMode,
    PHOTREE_DIR,
)

# Re-export album store functions
from ..album.store.fs import (  # noqa: F401
    discover_albums,
    discover_browsable_media_files,
    discover_media_sources,
    discover_potential_albums,
    has_media_sources,
    is_album,
    load_album_metadata,
    save_album_metadata,
)


# ---------------------------------------------------------------------------
# Gallery functions — defined here temporarily to avoid circular imports.
# Will move to gallery.store.fs once callers migrate off fs.
# ---------------------------------------------------------------------------


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
    """Resolve the gallery root directory."""
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
    """Walk up from *start_dir* looking for ``.photree/gallery.yaml``."""
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
