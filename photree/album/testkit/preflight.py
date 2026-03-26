"""Fake preflight check results for demo and testing purposes."""

from __future__ import annotations

from ...fsprotocol import MAIN_CONTRIBUTOR, plain_contributor
from ..preflight import (
    AlbumContributorSummary,
    AlbumDirCheck,
    AlbumPreflightResult,
)
from .integrity import FULL_INTEGRITY_FAILURES, FULL_INTEGRITY_OK

PREFLIGHT_OK = AlbumPreflightResult(
    sips_available=True,
    exiftool_available=True,
    contributor_summary=AlbumContributorSummary(contributors=(MAIN_CONTRIBUTOR,)),
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
    integrity=FULL_INTEGRITY_OK,
)

PREFLIGHT_FAILURES = AlbumPreflightResult(
    sips_available=False,
    exiftool_available=True,
    contributor_summary=AlbumContributorSummary(contributors=(MAIN_CONTRIBUTOR,)),
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
    integrity=FULL_INTEGRITY_FAILURES,
)

PREFLIGHT_OTHER = AlbumPreflightResult(
    sips_available=True,
    exiftool_available=True,
    contributor_summary=AlbumContributorSummary(
        contributors=(plain_contributor("main"),)
    ),
    dir_check=AlbumDirCheck(present=(), missing=()),
)
