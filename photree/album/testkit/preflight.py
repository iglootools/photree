"""Fake preflight check results for demo and testing purposes."""

from __future__ import annotations

from ..preflight import AlbumDirCheck, AlbumPreflightResult, AlbumType
from .integrity import INTEGRITY_FAILURES, INTEGRITY_OK

PREFLIGHT_OK = AlbumPreflightResult(
    sips_available=True,
    exiftool_available=True,
    album_type=AlbumType.IOS,
    dir_check=AlbumDirCheck(
        present=(
            "orig-img",
            "orig-vid",
            "edit-img",
            "edit-vid",
            "main-img",
            "main-vid",
            "main-jpg",
        ),
        missing=(),
    ),
    integrity=INTEGRITY_OK,
)

PREFLIGHT_FAILURES = AlbumPreflightResult(
    sips_available=False,
    exiftool_available=True,
    album_type=AlbumType.IOS,
    dir_check=AlbumDirCheck(
        present=("orig-img", "main-img"),
        missing=(
            "orig-vid",
            "edit-img",
            "edit-vid",
            "main-vid",
            "main-jpg",
        ),
    ),
    integrity=INTEGRITY_FAILURES,
)

PREFLIGHT_OTHER = AlbumPreflightResult(
    sips_available=True,
    exiftool_available=True,
    album_type=AlbumType.OTHER,
    dir_check=AlbumDirCheck(present=(), missing=()),
)
