"""Rendering of a face model archive that failed its pinned checksum."""

from photree.album.faces.model import ModelChecksumError
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
