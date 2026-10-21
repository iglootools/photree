"""How materialized files (browsable dirs, exports) reference their source."""

from enum import StrEnum


class LinkMode(StrEnum):
    """How main-dir files reference their source."""

    COPY = "copy"
    HARDLINK = "hardlink"
    SYMLINK = "symlink"
