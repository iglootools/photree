"""Fake validation errors for demo and testing purposes."""

from __future__ import annotations

from ..image_capture import ValidationError

VALIDATION_ERRORS = [
    ValidationError(
        "IMG_9999.HEIC",
        "no matching original found in Image Capture directory",
    ),
    ValidationError(
        "IMG_0410.HEIC",
        "rendered sidecar exists (IMG_O0410.AAE) but no rendered media file",
    ),
    ValidationError(
        "IMG_0500.HEIC",
        "original HEIC (IMG_0500.HEIC) has no AAE sidecar (unusual)",
    ),
]
