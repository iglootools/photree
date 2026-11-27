"""Rendering of filesystem errors (plain text, unindented)."""

from pathlib import Path

from photree.common.formatting import indent
from photree.common.fs import FileDeletionError, display_path


def format_file_deletion_error(exc: FileDeletionError, cwd: Path) -> str:
    """Return the lines reporting a deletion that stopped partway, and its state."""
    directory = display_path(exc.directory, cwd)
    return "\n".join(
        [
            f"Could not delete {exc.failed} from {directory}: {exc.reason}.",
            *(
                [
                    f"Already deleted from {directory} before it failed:",
                    *(indent(f) for f in exc.deleted),
                ]
                if exc.deleted
                else []
            ),
            f"Not deleted (still in {directory}):",
            *(indent(f) for f in (exc.failed, *exc.remaining)),
        ],
    )
