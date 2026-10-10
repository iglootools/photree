"""Export layout enums: how albums are organized within a share directory.

They live in the foundation layer (rather than in ``album.exporter``) so that
``clihelpers`` and ``config`` can reference them without depending on the
album package.
"""

from __future__ import annotations

from enum import StrEnum


class AlbumShareLayout(StrEnum):
    """How an album is exported."""

    BROWSABLE_JPG = "browsable-jpg"
    BROWSABLE = "browsable"
    ALL = "all"
    ARCHIVE = "archive"


class ShareDirectoryLayout(StrEnum):
    """How albums are organized within the share directory."""

    FLAT = "flat"
    ALBUMS = "albums"
    BY_MONTH = "by-month"
