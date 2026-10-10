"""Album storage protocol — the ``.photree/`` layout and the album metadata model."""

from __future__ import annotations

from pydantic import Field

from ...foundation.model import PhotreeModel

# ---------------------------------------------------------------------------
# On-disk layout (under the album's ``.photree/``)
# ---------------------------------------------------------------------------

ALBUM_YAML = "album.yaml"
MEDIA_IDS_DIR = "media-ids"
CACHE_DIR = "cache"


# ---------------------------------------------------------------------------
# Metadata model
# ---------------------------------------------------------------------------


class AlbumMetadata(PhotreeModel):
    """Per-album metadata stored in ``.photree/album.yaml``."""

    id: str = Field(description="UUID v7 identifying the album.")
