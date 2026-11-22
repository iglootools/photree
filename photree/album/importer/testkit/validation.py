"""Fake validation errors for demo and testing purposes."""

from photree.album.check.std import DuplicateStem
from photree.album.importer.album_import import TaskIssue
from photree.album.importer.image_capture import ValidationError, ValidationErrorKind
from photree.album.store.media_source import ios_media_source, std_media_source

VALIDATION_ERRORS = [
    TaskIssue(
        ios_media_source("main"),
        ValidationError("IMG_9999.HEIC", ValidationErrorKind.NO_MATCHING_ORIGINAL),
    ),
    TaskIssue(
        ios_media_source("main"),
        ValidationError(
            "IMG_0410.HEIC",
            ValidationErrorKind.ORPHAN_RENDERED_SIDECAR,
            img_number="0410",
            files=("IMG_O0410.AAE",),
        ),
    ),
    TaskIssue(
        std_media_source("nelu"),
        DuplicateStem(
            directory="orig",
            stem="photo1",
            files=("photo1.heic", "photo1.jpg"),
        ),
    ),
]
