"""
Output formatting for the per-file failures of a refresh of derived data.

The JPEG conversions and face detections that failed, shared by refresh,
import and gallery import.

Formatters return unindented lines; nested detail lines are indented relative
to their heading with :func:`~photree.common.formatting.indent`, and the call
site decides how deep the whole block sits.

Formatters return Rich markup: every user-derived value (album and media
source names, paths, filenames, issue messages) is escaped with
:func:`~photree.common.formatting.markup_escape` here, so callers print the
result with markup enabled and must not escape it again.
"""

from photree.album.faces.failures import FaceFailure, format_face_failures
from photree.album.jpeg import JpegConversionFailure
from photree.common.formatting import (
    CROSS,
    indent,
    markup_escape,
)


def jpeg_failures_report(
    failures: tuple[tuple[str, JpegConversionFailure], ...],
) -> str:
    """Format the files that could not be converted to JPEG, as Rich markup."""
    return "\n".join(
        [
            f"{CROSS} jpeg: {len(failures)} file(s) could not be converted",
            *(
                indent(
                    markup_escape(f"{source}/{failure.filename}: {failure.reason}"),
                    2,
                )
                for source, failure in failures
            ),
        ],
    )


def face_failures_report(failures: tuple[tuple[str, FaceFailure], ...]) -> str:
    """Format the images face detection failed on, as Rich markup."""
    return "\n".join(
        [
            f"{CROSS} face detection failed for {len(failures)} image(s)",
            *(
                indent(markup_escape(line), 2)
                for line in format_face_failures(failures)
            ),
        ],
    )


def derived_failures_report(
    jpeg_failures: tuple[tuple[str, JpegConversionFailure], ...],
    face_failures: tuple[tuple[str, FaceFailure], ...],
    album_dir: str,
) -> str:
    """
    Report the per-file failures of a refresh of derived data.

    Shared by every command that refreshes derived data (refresh, import,
    gallery import), so a partial refresh reads — and is retried — the same
    way everywhere. Rich markup, with user text escaped.
    """
    flag = markup_escape(f'--album-dir "{album_dir}"')
    return "\n".join(
        [
            *(
                [
                    jpeg_failures_report(jpeg_failures),
                    (
                        f"Run 'photree album refresh --refresh-jpeg {flag}'"
                        " to retry the conversions."
                    ),
                ]
                if jpeg_failures
                else []
            ),
            *(
                [
                    face_failures_report(face_failures),
                    (
                        f"Run 'photree album detect-faces {flag}'"
                        " to retry face detection."
                    ),
                ]
                if face_failures
                else []
            ),
        ],
    )
