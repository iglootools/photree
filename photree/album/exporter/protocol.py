"""Exporter protocol — enums for share/export layouts."""

from __future__ import annotations

from enum import StrEnum


class AlbumShareLayout(StrEnum):
    """How an album is exported."""

    MAIN_JPG = "main-jpg"
    MAIN = "main"
    ALL = "all"


class ShareDirectoryLayout(StrEnum):
    """How albums are organized within the share directory."""

    FLAT = "flat"
    ALBUMS = "albums"


SHARE_SENTINEL = ".photree-share"
