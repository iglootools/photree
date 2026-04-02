"""Filesystem protocol — backward-compatible re-export facade.

Canonical locations are now in domain store modules. This module
re-exports everything for backward compatibility during migration.
"""

from __future__ import annotations

from pydantic import Field

# Re-export shared foundation
from ..fsprotocol import (  # noqa: F401
    PHOTREE_DIR,
    LinkMode,
    _BaseModel,
    _to_kebab,
)

# Re-export exporter enums
from ..album.exporter.protocol import (  # noqa: F401
    SHARE_SENTINEL,
    AlbumShareLayout,
    ShareDirectoryLayout,
)

# Re-export album store protocol
from ..album.store.protocol import (  # noqa: F401
    ALBUM_DATE_RE,
    ALBUM_ID_PREFIX,
    ALBUM_YAML,
    CONVERT_TO_JPEG_EXTENSIONS,
    COPY_AS_IS_TO_JPEG_EXTENSIONS,
    DEFAULT_MEDIA_SOURCE,
    IMG_EXTENSIONS,
    IOS_DIR_PREFIX,
    IOS_IMG_EXTENSIONS,
    IOS_VID_EXTENSIONS,
    MAIN_MEDIA_SOURCE,
    PICTURE_PRIORITY_EXTENSIONS,
    SELECTION_DIR,
    SIDECAR_EXTENSIONS,
    STD_DIR_PREFIX,
    VID_EXTENSIONS,
    AlbumMetadata,
    MediaSource,
    MediaSourceType,
    _ALBUM_DATE_RE,
    _DATE_PART,
    _KeyFn,
    _stem_key,
    format_album_external_id,
    format_external_id,
    generate_album_id,
    ios_media_source,
    parse_album_year,
    parse_external_id,
    std_media_source,
)

# Gallery protocol — will move to gallery.store.protocol in Phase E
GALLERY_YAML = "gallery.yaml"


class GalleryMetadata(_BaseModel):
    """Gallery-wide metadata stored in ``.photree/gallery.yaml``."""

    link_mode: LinkMode = Field(
        default=LinkMode.HARDLINK,
        description="Default link mode for optimize and other link-mode operations.",
    )
