"""Text for a batch refresh (``albums refresh``, ``gallery refresh``): its failures."""

from photree.album.faces.failures import format_face_failures
from photree.albums.cmd_handler import describe_step_error
from photree.albums.cmd_handler.refresh import IncompleteRefreshError


def describe_refresh_error(exc: Exception) -> tuple[str, tuple[str, ...]]:
    """
    Word why an album of a batch refresh failed: its reason, then its labels.

    An album refreshed only in part gets one label per JPEG conversion and
    face detection that failed, and a reason joining them all. Plain text.
    """
    match exc:
        case IncompleteRefreshError(result=result):
            jpeg = tuple(
                f"{source}/{failure.filename}: {failure.reason}"
                for source, failure in result.jpeg_failures
            )
            faces = tuple(format_face_failures(result.face_failures))
            reason = "; ".join(
                [
                    *([f"jpeg conversion failed: {'; '.join(jpeg)}"] if jpeg else []),
                    *([f"face detection failed: {'; '.join(faces)}"] if faces else []),
                ],
            )
            return reason, (*jpeg, *faces)
        case _:
            return describe_step_error(exc)
