"""
Text for a batch refresh (``albums refresh``, ``gallery refresh``): its failures.

Also words the derived-data failures of a batch import, which ends with the
same refresh. Plain text.
"""

from photree.album.faces.failures import FaceFailure, format_face_failures
from photree.album.jpeg import JpegConversionFailure
from photree.albums.cmd_handler import describe_step_error
from photree.albums.cmd_handler.refresh import IncompleteRefreshError


def format_jpeg_failures(
    failures: tuple[tuple[str, JpegConversionFailure], ...],
) -> list[str]:
    """One unindented ``source/file: reason`` line per JPEG that failed to convert."""
    return [
        f"{source}/{failure.filename}: {failure.reason}" for source, failure in failures
    ]


def format_derived_failures(
    jpeg_failures: tuple[tuple[str, JpegConversionFailure], ...],
    face_failures: tuple[tuple[str, FaceFailure], ...],
) -> list[str]:
    """One phrase per kind of derived data that failed, naming every file."""
    jpeg = "; ".join(format_jpeg_failures(jpeg_failures))
    faces = "; ".join(format_face_failures(face_failures))
    return [
        *([f"jpeg conversion failed: {jpeg}"] if jpeg else []),
        *([f"face detection failed: {faces}"] if faces else []),
    ]


def describe_refresh_error(exc: Exception) -> tuple[str, tuple[str, ...]]:
    """
    Word why an album of a batch refresh failed: its reason, then its labels.

    An album refreshed only in part gets one label per JPEG conversion and
    face detection that failed, and a reason joining them all.
    """
    match exc:
        case IncompleteRefreshError(result=result):
            return (
                "; ".join(
                    format_derived_failures(result.jpeg_failures, result.face_failures),
                ),
                (
                    *format_jpeg_failures(result.jpeg_failures),
                    *format_face_failures(result.face_failures),
                ),
            )
        case _:
            return describe_step_error(exc)
