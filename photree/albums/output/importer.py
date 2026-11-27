"""
User-facing messages for a batch import (``albums import``).

:func:`failure_reason` is plain text; the other formatters return Rich markup
with user-derived text (paths, reasons) escaped via ``markup_escape``, to
print with markup enabled.
"""

from collections.abc import Sequence
from pathlib import Path

from photree.album.importer.album_import import (
    EmptyImageCaptureDirError,
    NoImportTasksError,
)
from photree.album.importer.output import import_refusal
from photree.albums.cmd_handler.importer import AlbumFailure
from photree.albums.output.refresh import format_derived_failures
from photree.common.formatting import indent, markup_escape
from photree.common.fs import display_path


def failure_reason(failure: AlbumFailure, cwd: Path) -> str:
    """
    Word why an album of a batch failed to import (plain text).

    A refusal or a filesystem error that stopped the import, or every part
    that failed after a completed import.
    """
    match failure.error:
        case None:
            return _partial_failure_reason(failure)
        case NoImportTasksError() | EmptyImageCaptureDirError() as refusal:
            return import_refusal(refusal, cwd)
        case OSError(filename=str() | Path() as filename) as error:
            return (
                f"{error.strerror or type(error).__name__}: "
                f"{display_path(Path(filename), cwd)}"
            )
        case error:
            return str(error)


def _partial_failure_reason(failure: AlbumFailure) -> str:
    """Join what failed after a completed import, in the order it ran."""
    return "; ".join(
        [
            *(
                [f"selection entries left behind: {', '.join(failure.unprocessed)}"]
                if failure.unprocessed
                else []
            ),
            *format_derived_failures(failure.jpeg_failures, failure.face_failures),
        ],
    )


def batch_summary(
    imported: int,
    skipped: int,
    failed: int = 0,
    *,
    dry_run: bool = False,
) -> str:
    """Return the closing tally of a batch import, worded for a *dry_run* too."""
    tally = (
        f"{imported} album(s) would be imported"
        if dry_run
        else f"Done. {imported} album(s) imported"
    )
    return f"\n{tally}, {failed} failed, {skipped} skipped."


def batch_failures(failures: Sequence[AlbumFailure], base: Path) -> str:
    """
    Report each album that failed, with its reason.

    The reason is what the batch loop swallowed previously; without it a run
    where every album failed was indistinguishable from one where every album
    was skipped.
    """
    return "\n".join(
        [
            "\nFailed albums:",
            *(
                indent(
                    f"{markup_escape(display_path(failure.album_dir, base))}\n"
                    f"{indent(markup_escape(failure_reason(failure, base)))}",
                )
                for failure in failures
            ),
        ],
    )
