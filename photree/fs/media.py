"""Generic media matching — backward-compatible re-export facade.

Canonical location: :mod:`album.store.media_sources`.
"""

from __future__ import annotations

from ..album.store.media_sources import (  # noqa: F401
    dedup_media_dict,
    find_files_by_key,
    group_by_key,
    pick_media_priority,
)
from ..album.store.protocol import PICTURE_PRIORITY_EXTENSIONS  # noqa: F401
