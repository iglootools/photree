"""The names of an album's metadata files and the model of ``album.yaml``."""

from pydantic import Field

from photree.foundation.model import PhotreeModel

ALBUM_YAML = "album.yaml"
MEDIA_IDS_DIR = "media-ids"
CACHE_DIR = "cache"


class AlbumMetadata(PhotreeModel):
    """Per-album metadata stored in ``.photree/album.yaml``."""

    id: str = Field(description="UUID v7 identifying the album.")
