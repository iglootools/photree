"""Fake integrity check results for demo and testing purposes."""

from __future__ import annotations

from ...fsprotocol import MAIN_MEDIA_SOURCE
from ..integrity import (
    CombinedDirCheck,
    FileComparison,
    IosAlbumFullIntegrityResult,
    IosAlbumIntegrityResult,
    JpegCheck,
    MissingFile,
    SidecarCheck,
)

INTEGRITY_OK = IosAlbumIntegrityResult(
    combined_heic=CombinedDirCheck(
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
    combined_mov=CombinedDirCheck(
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
    combined_heic=CombinedDirCheck(
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
    combined_mov=CombinedDirCheck(
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
