"""Gallery protocol — metadata model and constants."""

from __future__ import annotations

from pydantic import Field

from ...fsprotocol import LinkMode, _BaseModel

GALLERY_YAML = "gallery.yaml"


class GalleryMetadata(_BaseModel):
    """Gallery-wide metadata stored in ``.photree/gallery.yaml``."""

    link_mode: LinkMode = Field(
        default=LinkMode.HARDLINK,
        description="Default link mode for optimize and other link-mode operations.",
    )
