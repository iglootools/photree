"""Fake check results for demo and testing purposes."""

from __future__ import annotations

from . import (
    AlbumDirCheck,
    AlbumIdCheck,
    AlbumIntegrityResult,
    AlbumMediaSourceSummary,
    AlbumPreflightResult,
)
from ..store.protocol import MAIN_MEDIA_SOURCE, std_media_source
from .browsable import BrowsableDirCheck, FileComparison, MissingFile
from .ios import IosMediaSourceIntegrityResult
from .unexpected_dirs import UnexpectedDirsCheck
from .ios.sidecar import SidecarCheck
from .jpeg import AlbumJpegIntegrityResult, JpegCheck
from .std import StdMediaSourceIntegrityResult

_STD_MEDIA_SOURCE = std_media_source("nelu")

# ---------------------------------------------------------------------------
# Browsable dir check fixtures
# ---------------------------------------------------------------------------

_BROWSABLE_OK = BrowsableDirCheck(
    correct=(
        FileComparison("IMG_E0001.HEIC", "IMG_E0001.HEIC", True, True),
        FileComparison("IMG_0002.PNG", "IMG_0002.PNG", True, True),
    ),
    missing=(),
    extra=(),
    wrong_source=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

_BROWSABLE_VID_OK = BrowsableDirCheck(
    correct=(FileComparison("IMG_0003.MOV", "IMG_0003.MOV", True, True),),
    missing=(),
    extra=(),
    wrong_source=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

_BROWSABLE_EMPTY = BrowsableDirCheck(
    correct=(),
    missing=(),
    extra=(),
    wrong_source=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

_BROWSABLE_FAILURES = BrowsableDirCheck(
    correct=(),
    missing=(MissingFile("IMG_E0001.HEIC", "edit-img"),),
    extra=("STRAY_FILE.HEIC",),
    wrong_source=("IMG_0002.HEIC (should be IMG_E0002.HEIC, edited version exists)",),
    size_mismatches=(FileComparison("IMG_0003.HEIC", "IMG_0003.HEIC", False, None),),
    checksum_mismatches=(),
)

# ---------------------------------------------------------------------------
# JPEG check fixtures
# ---------------------------------------------------------------------------

_JPEG_OK = JpegCheck(present=("IMG_E0001.jpg", "IMG_0002.PNG"), missing=(), extra=())

_JPEG_FAILURES = JpegCheck(
    present=(),
    missing=("IMG_E0001.jpg",),
    extra=("ORPHAN.jpg",),
)

# ---------------------------------------------------------------------------
# iOS media source integrity fixtures
# ---------------------------------------------------------------------------

IOS_INTEGRITY_OK = IosMediaSourceIntegrityResult(
    browsable_img=_BROWSABLE_OK,
    browsable_vid=_BROWSABLE_VID_OK,
    browsable_jpg=_JPEG_OK,
    sidecars=SidecarCheck(missing_sidecars=(), orphan_sidecars=()),
)

IOS_INTEGRITY_FAILURES = IosMediaSourceIntegrityResult(
    browsable_img=_BROWSABLE_FAILURES,
    browsable_vid=_BROWSABLE_EMPTY,
    browsable_jpg=_JPEG_FAILURES,
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

# ---------------------------------------------------------------------------
# Std media source integrity fixtures
# ---------------------------------------------------------------------------

_STD_BROWSABLE_OK = BrowsableDirCheck(
    correct=(
        FileComparison("photo1.heic", "photo1.heic", True, True),
        FileComparison("photo2.jpg", "photo2.jpg", True, True),
    ),
    missing=(),
    extra=(),
    wrong_source=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

_STD_VID_OK = BrowsableDirCheck(
    correct=(FileComparison("clip1.mov", "clip1.mov", True, True),),
    missing=(),
    extra=(),
    wrong_source=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

STD_INTEGRITY_OK = StdMediaSourceIntegrityResult(
    browsable_img=_STD_BROWSABLE_OK,
    browsable_vid=_STD_VID_OK,
    browsable_jpg=JpegCheck(present=("photo1.jpg", "photo2.jpg"), missing=(), extra=()),
)

STD_INTEGRITY_FAILURES = StdMediaSourceIntegrityResult(
    browsable_img=BrowsableDirCheck(
        correct=(),
        missing=(MissingFile("photo1.heic", "orig-img"),),
        extra=("stray.png",),
        wrong_source=(),
        size_mismatches=(),
        checksum_mismatches=(),
    ),
    browsable_vid=_BROWSABLE_EMPTY,
    browsable_jpg=JpegCheck(present=(), missing=("photo1.jpg",), extra=()),
    duplicate_stems=(
        "orig-img/: stem photo2 has multiple media files: photo2.heic, photo2.jpg",
    ),
)

# ---------------------------------------------------------------------------
# Unified album integrity fixtures
# ---------------------------------------------------------------------------

INTEGRITY_OK = AlbumIntegrityResult(
    by_media_source=((MAIN_MEDIA_SOURCE, IOS_INTEGRITY_OK),)
)

INTEGRITY_FAILURES = AlbumIntegrityResult(
    by_media_source=((MAIN_MEDIA_SOURCE, IOS_INTEGRITY_FAILURES),)
)

INTEGRITY_MIXED_OK = AlbumIntegrityResult(
    by_media_source=(
        (MAIN_MEDIA_SOURCE, IOS_INTEGRITY_OK),
        (_STD_MEDIA_SOURCE, STD_INTEGRITY_OK),
    )
)

# ---------------------------------------------------------------------------
# JPEG album-wide integrity fixtures
# ---------------------------------------------------------------------------

JPEG_INTEGRITY_OK = AlbumJpegIntegrityResult(
    by_media_source=(
        (MAIN_MEDIA_SOURCE, _JPEG_OK),
        (_STD_MEDIA_SOURCE, JpegCheck(present=("photo1.jpg",), missing=(), extra=())),
    )
)

JPEG_INTEGRITY_FAILURES = AlbumJpegIntegrityResult(
    by_media_source=((MAIN_MEDIA_SOURCE, _JPEG_FAILURES),)
)

# ---------------------------------------------------------------------------
# Preflight fixtures
# ---------------------------------------------------------------------------

_IOS_DIR_CHECK_OK = AlbumDirCheck(
    present=(
        "ios-main/orig-img",
        "ios-main/orig-vid",
        "main-img",
        "main-vid",
        "main-jpg",
    ),
    missing=(),
    optional_present=("ios-main/edit-img", "ios-main/edit-vid"),
    optional_absent=(),
)

PREFLIGHT_OK = AlbumPreflightResult(
    sips_available=True,
    exiftool_available=True,
    media_source_summary=AlbumMediaSourceSummary(media_sources=(MAIN_MEDIA_SOURCE,)),
    dir_check=_IOS_DIR_CHECK_OK,
    album_id_check=AlbumIdCheck(
        has_id=True, album_id="01234567-89ab-7def-8123-456789abcdef"
    ),
    unexpected_dirs_check=UnexpectedDirsCheck(unexpected=()),
    integrity=INTEGRITY_OK,
    jpeg_check=JPEG_INTEGRITY_OK,
)

PREFLIGHT_FAILURES = AlbumPreflightResult(
    sips_available=False,
    exiftool_available=True,
    media_source_summary=AlbumMediaSourceSummary(media_sources=(MAIN_MEDIA_SOURCE,)),
    dir_check=AlbumDirCheck(
        present=("ios-main/orig-img", "main-img"),
        missing=(
            "ios-main/orig-vid",
            "main-vid",
            "main-jpg",
        ),
    ),
    album_id_check=AlbumIdCheck(has_id=False),
    integrity=INTEGRITY_FAILURES,
    jpeg_check=JPEG_INTEGRITY_FAILURES,
)

PREFLIGHT_STD = AlbumPreflightResult(
    sips_available=True,
    exiftool_available=True,
    media_source_summary=AlbumMediaSourceSummary(
        media_sources=(std_media_source("main"),)
    ),
    dir_check=AlbumDirCheck(
        present=("std-main/orig-img", "main-img", "main-jpg"),
        missing=(),
    ),
    album_id_check=AlbumIdCheck(
        has_id=True, album_id="01234567-89ab-7def-8123-456789abcdef"
    ),
    unexpected_dirs_check=UnexpectedDirsCheck(unexpected=()),
    integrity=AlbumIntegrityResult(
        by_media_source=((std_media_source("main"), STD_INTEGRITY_OK),)
    ),
    jpeg_check=JPEG_INTEGRITY_OK,
)
