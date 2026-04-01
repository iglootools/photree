"""Fake preflight check results for demo and testing purposes."""

from __future__ import annotations

from ...fs import MAIN_MEDIA_SOURCE, plain_media_source
from . import (
    AlbumMediaSourceSummary,
    AlbumDirCheck,
    AlbumPreflightResult,
)
from ..integrity.testkit import FULL_INTEGRITY_FAILURES, FULL_INTEGRITY_OK

PREFLIGHT_OK = AlbumPreflightResult(
    sips_available=True,
    exiftool_available=True,
    media_source_summary=AlbumMediaSourceSummary(media_sources=(MAIN_MEDIA_SOURCE,)),
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
    ios_integrity=FULL_INTEGRITY_OK,
)

PREFLIGHT_FAILURES = AlbumPreflightResult(
    sips_available=False,
    exiftool_available=True,
    media_source_summary=AlbumMediaSourceSummary(media_sources=(MAIN_MEDIA_SOURCE,)),
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
    ios_integrity=FULL_INTEGRITY_FAILURES,
)

PREFLIGHT_OTHER = AlbumPreflightResult(
    sips_available=True,
    exiftool_available=True,
    media_source_summary=AlbumMediaSourceSummary(
        media_sources=(plain_media_source("main"),)
    ),
    dir_check=AlbumDirCheck(present=(), missing=()),
)
