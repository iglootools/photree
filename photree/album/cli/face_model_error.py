"""Rendering of a face model archive that failed its download or pinned checksum."""

from photree.album.faces.model import (
    ModelChecksumError,
    ModelDownloadError,
    ModelDownloadFailureKind,
)
from photree.common.formatting import indent


def format_model_checksum_error(exc: ModelChecksumError) -> str:
    """Return the plain-text report of *exc*: the URL, both hashes, what to do."""
    return "\n".join(
        [
            "The face model archive does not have the sha256 photree pins:",
            indent(f"URL:      {exc.url}"),
            indent(f"expected: {exc.expected}"),
            indent(f"actual:   {exc.actual}"),
            (
                "Nothing was installed. A transfer error is fixed by running the "
                "command again; if the hash still differs, the archive was "
                "replaced upstream: report it at "
                "https://github.com/iglootools/photree/issues."
            ),
        ],
    )


def format_model_download_error(exc: ModelDownloadError) -> str:
    """Return the plain-text report of *exc*: the URL, the cause, what to do."""
    match exc.kind:
        case ModelDownloadFailureKind.TIMED_OUT:
            headline = "The face model download stalled and timed out:"
        case ModelDownloadFailureKind.UNREACHABLE:
            headline = "The face model archive could not be downloaded:"
    return "\n".join(
        [
            headline,
            indent(f"URL:   {exc.url}"),
            indent(f"cause: {exc.detail}"),
            (
                "Nothing was installed. Check the network connection, then run the "
                "command again."
            ),
        ],
    )
