"""EXIF cache protocol — constants and models."""

from __future__ import annotations

from pydantic import Field

from ...fsprotocol import PhotreeModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXIF_CACHE_DIR = "cache/exif"
"""Subdirectory under ``.photree/`` for EXIF timestamp cache."""

EXIF_CACHE_VERSION = 2
"""Current cache layout version.

Version 1 keyed entries by bare filename stem across ``{name}-jpg/`` and
``{name}-vid/`` and stored bare filenames, so ``clip.jpg`` and ``clip.mp4``
collided and videos were reported under the JPEG directory. Version 2 keys
entries by ``{subdir}/{stem}`` and stores the album-relative path. Older
caches are not migrated: they are treated as absent and rebuilt by the next
refresh.
"""


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ExifCacheEntry(PhotreeModel):
    """Cached EXIF timestamp for a single media file."""

    mtime: float = Field(description="File modification time at cache time.")
    file_name: str = Field(
        description=(
            "Album-relative path of the browsable file "
            "(e.g. ``main-vid/IMG_0115.MOV``); a bare filename in version 1."
        )
    )
    timestamp: str | None = Field(
        description="ISO-format EXIF timestamp, or None if no timestamp found."
    )


class ExifCache(PhotreeModel):
    """Per-media-source EXIF timestamp cache in ``.photree/cache/exif/{name}.yaml``.

    ``files`` is keyed by ``{subdir}/{stem}`` (e.g. ``main-jpg/IMG_0410``).
    """

    version: int = Field(
        default=1,
        description="Cache layout version; files without the field are version 1.",
    )
    files: dict[str, ExifCacheEntry] = Field(default_factory=dict)

    @property
    def is_current(self) -> bool:
        return self.version == EXIF_CACHE_VERSION
