"""EXIF cache protocol — constants and models."""

from __future__ import annotations

from pydantic import Field

from ...fsprotocol import _BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIF_CACHE_DIR = "exif-cache"
"""Subdirectory under ``.photree/`` for EXIF timestamp cache."""


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExifCacheEntry(_BaseModel):
    """Cached EXIF timestamp for a single media file."""

    mtime: float = Field(description="File modification time at cache time.")
    file_name: str = Field(description="Browsable filename (for logging).")
    timestamp: str | None = Field(
        description="ISO-format EXIF timestamp, or None if no timestamp found."
    )


class ExifCache(_BaseModel):
    """Per-media-source EXIF timestamp cache stored in ``.photree/exif-cache/{name}.yaml``."""

    files: dict[str, ExifCacheEntry] = Field(default_factory=dict)
