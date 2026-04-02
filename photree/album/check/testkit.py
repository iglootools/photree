"""Fake check results for demo and testing purposes."""

from __future__ import annotations

from ..store.protocol import MAIN_MEDIA_SOURCE, std_media_source
from . import (
    AlbumDirCheck,
    AlbumMediaSourceSummary,
    AlbumPreflightResult,
)
from .browsable import BrowsableDirCheck, FileComparison, MissingFile
from .ios import (
    IosAlbumFullIntegrityResult,
    IosAlbumIntegrityResult,
)
from .jpeg import JpegCheck
from .sidecar import SidecarCheck

# ---------------------------------------------------------------------------
# Integrity testkit (was album/integrity/testkit.py)
# ---------------------------------------------------------------------------

INTEGRITY_OK = IosAlbumIntegrityResult(
    browsable_img=BrowsableDirCheck(
        correct=(
            FileComparison("IMG_E0001.HEIC", "IMG_E0001.HEIC", True, True),
            FileComparison("IMG_0002.PNG", "IMG_0002.PNG", True, True),
        ),
        missing=(),
        extra=(),
        wrong_source=(),
        size_mismatches=(),
        checksum_mismatches=(),
    ),
    browsable_vid=BrowsableDirCheck(
        correct=(FileComparison("IMG_0003.MOV", "IMG_0003.MOV", True, True),),
        missing=(),
        extra=(),
        wrong_source=(),
        size_mismatches=(),
        checksum_mismatches=(),
    ),
    jpeg=JpegCheck(present=("IMG_E0001.jpg", "IMG_0002.PNG"), missing=(), extra=()),
    sidecars=SidecarCheck(missing_sidecars=(), orphan_sidecars=()),
)

INTEGRITY_FAILURES = IosAlbumIntegrityResult(
    browsable_img=BrowsableDirCheck(
        correct=(),
        missing=(MissingFile("IMG_E0001.HEIC", "edit-img"),),
        extra=("STRAY_FILE.HEIC",),
        wrong_source=(
            "IMG_0002.HEIC (should be IMG_E0002.HEIC, edited version exists)",
        ),
        size_mismatches=(
            FileComparison("IMG_0003.HEIC", "IMG_0003.HEIC", False, None),
        ),
        checksum_mismatches=(),
    ),
    browsable_vid=BrowsableDirCheck(
        correct=(),
        missing=(),
        extra=(),
        wrong_source=(),
        size_mismatches=(),
        checksum_mismatches=(),
    ),
    jpeg=JpegCheck(
        present=(),
        missing=("IMG_E0001.jpg",),
        extra=("ORPHAN.jpg",),
    ),
    sidecars=SidecarCheck(
        missing_sidecars=(
            "IMG_0001.HEIC has no AAE sidecar in orig-img/",
            "IMG_E0002.HEIC has no O-prefixed AAE sidecar in edit-img/",
        ),
        orphan_sidecars=("IMG_9999.AAE has no matching media file in orig-img/",),
    ),
    miscategorized=(
        "IMG_E0410.HEIC in orig-img/ looks like an edited file (IMG_E prefix)",
        "IMG_0100.HEIC in edit-img/ looks like an original file (no E/O prefix)",
    ),
)

# Wrapped in IosAlbumFullIntegrityResult for preflight tests
FULL_INTEGRITY_OK = IosAlbumFullIntegrityResult(
    by_media_source=((MAIN_MEDIA_SOURCE, INTEGRITY_OK),)
)

FULL_INTEGRITY_FAILURES = IosAlbumFullIntegrityResult(
    by_media_source=((MAIN_MEDIA_SOURCE, INTEGRITY_FAILURES),)
)

# ---------------------------------------------------------------------------
# Preflight testkit (was album/preflight/testkit.py)
# ---------------------------------------------------------------------------

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
        media_sources=(std_media_source("main"),)
    ),
    dir_check=AlbumDirCheck(present=(), missing=()),
)
