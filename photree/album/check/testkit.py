"""Fake check results for demo and testing purposes."""

from dataclasses import replace

from photree.album.check import (
    AlbumDirCheck,
    AlbumIdCheck,
    AlbumIntegrityResult,
    AlbumMediaSourceSummary,
    AlbumPreflightResult,
)
from photree.album.check.browsable import (
    BrowsableDirCheck,
    FileComparison,
    MissingFile,
    WrongSource,
)
from photree.album.check.exif_date import (
    AlbumNamingResult,
    ExifMismatch,
    ExifTimestampCheck,
)
from photree.album.check.ios import (
    IosMediaSourceIntegrityResult,
    MiscategorizedFile,
    MiscategorizedKind,
)
from photree.album.check.ios.sidecar import SidecarCheck, SidecarIssue, SidecarIssueKind
from photree.album.check.jpeg import AlbumJpegIntegrityResult, JpegCheck
from photree.album.check.std import DuplicateStem, StdMediaSourceIntegrityResult
from photree.album.check.unexpected_dirs import UnexpectedDirsCheck
from photree.album.naming import parse_album_name
from photree.album.store.media_source import MAIN_MEDIA_SOURCE, std_media_source

_STD_MEDIA_SOURCE = std_media_source("nelu")


_BROWSABLE_OK = BrowsableDirCheck(
    correct=(
        FileComparison(
            "IMG_E0001.HEIC",
            "IMG_E0001.HEIC",
            size_match=True,
            checksum_match=True,
        ),
        FileComparison(
            "IMG_0002.PNG",
            "IMG_0002.PNG",
            size_match=True,
            checksum_match=True,
        ),
    ),
    missing=(),
    extra=(),
    wrong_source=(),
    wrong_link_mode=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

_BROWSABLE_VID_OK = BrowsableDirCheck(
    correct=(
        FileComparison(
            "IMG_0003.MOV",
            "IMG_0003.MOV",
            size_match=True,
            checksum_match=True,
        ),
    ),
    missing=(),
    extra=(),
    wrong_source=(),
    wrong_link_mode=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

_BROWSABLE_EMPTY = BrowsableDirCheck(
    correct=(),
    missing=(),
    extra=(),
    wrong_source=(),
    wrong_link_mode=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

_BROWSABLE_FAILURES = BrowsableDirCheck(
    correct=(),
    missing=(MissingFile("IMG_E0001.HEIC", "edit-img"),),
    extra=("STRAY_FILE.HEIC",),
    wrong_source=(WrongSource("IMG_0002.HEIC", "IMG_E0002.HEIC"),),
    wrong_link_mode=(),
    size_mismatches=(
        FileComparison(
            "IMG_0003.HEIC",
            "IMG_0003.HEIC",
            size_match=False,
            checksum_match=None,
        ),
    ),
    checksum_mismatches=(),
)


_JPEG_OK = JpegCheck(present=("IMG_E0001.jpg", "IMG_0002.PNG"), missing=(), extra=())

_JPEG_FAILURES = JpegCheck(
    present=(),
    missing=("IMG_E0001.jpg",),
    extra=("ORPHAN.jpg",),
)


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
            SidecarIssue("IMG_0001.HEIC", "orig-img", SidecarIssueKind.MISSING_SIDECAR),
            SidecarIssue(
                "IMG_E0002.HEIC",
                "edit-img",
                SidecarIssueKind.MISSING_EDIT_SIDECAR,
            ),
        ),
        orphan_sidecars=(
            SidecarIssue("IMG_9999.AAE", "orig-img", SidecarIssueKind.ORPHAN_SIDECAR),
        ),
    ),
    miscategorized=(
        MiscategorizedFile(
            "IMG_E0410.HEIC",
            "orig-img",
            MiscategorizedKind.EDITED_IN_ORIG,
        ),
        MiscategorizedFile(
            "IMG_0100.HEIC",
            "edit-img",
            MiscategorizedKind.ORIGINAL_IN_EDIT,
        ),
    ),
)


_STD_BROWSABLE_OK = BrowsableDirCheck(
    correct=(
        FileComparison(
            "photo1.heic",
            "photo1.heic",
            size_match=True,
            checksum_match=True,
        ),
        FileComparison(
            "photo2.jpg",
            "photo2.jpg",
            size_match=True,
            checksum_match=True,
        ),
    ),
    missing=(),
    extra=(),
    wrong_source=(),
    wrong_link_mode=(),
    size_mismatches=(),
    checksum_mismatches=(),
)

_STD_VID_OK = BrowsableDirCheck(
    correct=(
        FileComparison("clip1.mov", "clip1.mov", size_match=True, checksum_match=True),
    ),
    missing=(),
    extra=(),
    wrong_source=(),
    wrong_link_mode=(),
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
        wrong_link_mode=(),
        size_mismatches=(),
        checksum_mismatches=(),
    ),
    browsable_vid=_BROWSABLE_EMPTY,
    browsable_jpg=JpegCheck(present=(), missing=("photo1.jpg",), extra=()),
    duplicate_stems=(
        DuplicateStem("orig-img", "photo2", ("photo2.heic", "photo2.jpg")),
    ),
)


INTEGRITY_OK = AlbumIntegrityResult(
    by_media_source=((MAIN_MEDIA_SOURCE, IOS_INTEGRITY_OK),),
)

INTEGRITY_FAILURES = AlbumIntegrityResult(
    by_media_source=((MAIN_MEDIA_SOURCE, IOS_INTEGRITY_FAILURES),),
)

JPEG_INTEGRITY_OK = AlbumJpegIntegrityResult(
    by_media_source=(
        (MAIN_MEDIA_SOURCE, _JPEG_OK),
        (_STD_MEDIA_SOURCE, JpegCheck(present=("photo1.jpg",), missing=(), extra=())),
    ),
)

JPEG_INTEGRITY_FAILURES = AlbumJpegIntegrityResult(
    by_media_source=((MAIN_MEDIA_SOURCE, _JPEG_FAILURES),),
)


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
    media_source_summary=AlbumMediaSourceSummary(media_sources=(MAIN_MEDIA_SOURCE,)),
    dir_check=_IOS_DIR_CHECK_OK,
    album_id_check=AlbumIdCheck(
        has_id=True,
        album_id="01234567-89ab-7def-8123-456789abcdef",
    ),
    unexpected_dirs_check=UnexpectedDirsCheck(unexpected=()),
    integrity=INTEGRITY_OK,
    jpeg_check=JPEG_INTEGRITY_OK,
)

PREFLIGHT_FAILURES = AlbumPreflightResult(
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
    media_source_summary=AlbumMediaSourceSummary(
        media_sources=(std_media_source("main"),),
    ),
    dir_check=AlbumDirCheck(
        present=("std-main/orig-img", "main-img", "main-jpg"),
        missing=(),
    ),
    album_id_check=AlbumIdCheck(
        has_id=True,
        album_id="01234567-89ab-7def-8123-456789abcdef",
    ),
    unexpected_dirs_check=UnexpectedDirsCheck(unexpected=()),
    integrity=AlbumIntegrityResult(
        by_media_source=((std_media_source("main"), STD_INTEGRITY_OK),),
    ),
    jpeg_check=JPEG_INTEGRITY_OK,
)


# Albums that pass every check but carry one kind of warning, which the fatal
# flags promote to a failure.

PREFLIGHT_SIDECAR_WARNING = replace(
    PREFLIGHT_OK,
    integrity=AlbumIntegrityResult(
        by_media_source=(
            (
                MAIN_MEDIA_SOURCE,
                replace(
                    IOS_INTEGRITY_OK,
                    sidecars=SidecarCheck(
                        missing_sidecars=(
                            SidecarIssue(
                                "IMG_0001.HEIC",
                                "orig-img",
                                SidecarIssueKind.MISSING_SIDECAR,
                            ),
                        ),
                        orphan_sidecars=(),
                    ),
                ),
            ),
        ),
    ),
)

PREFLIGHT_EXIF_WARNING = replace(
    PREFLIGHT_OK,
    naming=AlbumNamingResult(
        parsed=parse_album_name("2024-07-20 - Beach"),
        issues=(),
        exif_check=ExifTimestampCheck(
            album_date="2024-07-20",
            mismatches=(ExifMismatch("main-img/IMG_0001.HEIC", "2023-01-01T10:00:00"),),
        ),
    ),
)
