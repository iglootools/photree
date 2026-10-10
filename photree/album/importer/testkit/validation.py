"""Fake validation errors for demo and testing purposes."""

from __future__ import annotations

from ...check.std import DuplicateStem
from ...store.media_source import ios_media_source, std_media_source
from ..album_import import TaskIssue
from ..image_capture import ValidationError, ValidationErrorKind

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
            directory="orig", stem="photo1", files=("photo1.heic", "photo1.jpg")
        ),
    ),
]
