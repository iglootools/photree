"""Gallery protocol — metadata model and constants.

Note: During the facade migration phase, GalleryMetadata and
GALLERY_YAML are defined in fs/protocol.py and re-exported here.
Once callers migrate to gallery.store.protocol directly (Phase F),
the definitions will move here and the fs facade dependency is removed.
"""

from __future__ import annotations

from ...fs.protocol import GALLERY_YAML, GalleryMetadata  # noqa: F401
