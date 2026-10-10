"""Face pipeline failure records — pure data, no ML dependencies.

Kept apart from :mod:`.refresh` so the check/import/refresh output layers can
report failures without importing the face-detection stack at CLI startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FaceFailureStage(StrEnum):
    """Pipeline stage at which an image failed."""

    THUMBNAIL = "thumbnail"
    DETECTION = "detection"


@dataclass(frozen=True)
class FaceFailure:
    """One image that could not be thumbnailed or analysed."""

    key: str
    stage: FaceFailureStage
    reason: str


def format_face_failures(
    failures: tuple[tuple[str, FaceFailure], ...],
) -> list[str]:
    """One unindented ``source/key (stage): reason`` line per failed image."""
    return [
        f"{ms_name}/{failure.key} ({failure.stage}): {failure.reason}"
        for ms_name, failure in failures
    ]
