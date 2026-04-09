"""Face detection protocol — constants, models, and type definitions."""

from __future__ import annotations

from pydantic import Field

from ...fsprotocol import _BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FACES_DIR = "faces-cache"
"""Subdirectory under ``.photree/`` for face detection cache (album-level)."""

FACES_STATE_SUFFIX = ".yaml"
"""Suffix for per-media-source processing state files."""

FACES_DATA_SUFFIX = ".npz"
"""Suffix for per-media-source face data (numpy compressed)."""

THUMBS_DIR_SUFFIX = "-thumbs"
"""Suffix for per-media-source thumbnail directories (e.g. ``main-thumbs``)."""

THUMB_MAX_DIMENSION = 640
"""Maximum pixel dimension for face detection thumbnails."""

DEFAULT_MODEL_NAME = "buffalo_l"
DEFAULT_MODEL_VERSION = "1.0"

# InsightFace embedding dimension for buffalo_l / ArcFace
EMBEDDING_DIM = 512


# ---------------------------------------------------------------------------
# Pydantic models — processing state (.yaml sidecar)
# ---------------------------------------------------------------------------


class FaceProcessedKey(_BaseModel):
    """Processing state for a single media key."""

    mtime: float = Field(description="File modification time at processing time.")
    file_name: str = Field(description="Original filename (for logging/debugging).")
    face_count: int = Field(description="Number of faces detected (0 = no faces).")
    orig_width: int = Field(description="Original image width in pixels.")
    orig_height: int = Field(description="Original image height in pixels.")
    thumb_width: int = Field(description="Thumbnail width after aspect-ratio resize.")
    thumb_height: int = Field(description="Thumbnail height after aspect-ratio resize.")


class FaceProcessingState(_BaseModel):
    """Per-media-source face detection state stored in ``.photree/faces/{name}.yaml``."""

    model_name: str = Field(default=DEFAULT_MODEL_NAME)
    model_version: str = Field(default=DEFAULT_MODEL_VERSION)
    processed_keys: dict[str, FaceProcessedKey] = Field(default_factory=dict)
