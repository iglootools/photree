"""Media file formats photree recognizes, and how each one is handled.

Domain knowledge (see docs/domain.md, "Supported formats"), independent of
where files are stored: which extensions are images, videos, or iOS sidecars,
which ones convert to JPEG, and which variant wins when several share a key.
"""

from __future__ import annotations

# All recognized media formats
IMG_EXTENSIONS = frozenset({".dng", ".heic", ".heif", ".jpeg", ".jpg", ".png"})
VID_EXTENSIONS = frozenset({".avi", ".mov", ".mp4", ".wmv"})

# iOS-specific subsets (used by importer, iOS fixes, integrity checks)
IOS_IMG_EXTENSIONS = frozenset({".dng", ".heic", ".heif", ".jpeg", ".jpg", ".png"})
IOS_VID_EXTENSIONS = frozenset({".mov"})
IOS_SIDECAR_EXTENSIONS = frozenset({".aae"})

# JPEG conversion — formats sips can convert to JPEG
CONVERT_TO_JPEG_EXTENSIONS = frozenset({".dng", ".heic", ".heif"})
COPY_AS_IS_TO_JPEG_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

# Preferred formats when multiple variants exist for the same key.
# DNG (ProRAW) is the highest-quality format, followed by HEIC (native iPhone).
# Tuple (not set) to express priority order: first match wins.
PICTURE_PRIORITY_EXTENSIONS = (".dng", ".heic")
