"""Text the CLI prints for a batch export: its summary and failures."""

from collections.abc import Sequence
from pathlib import Path

from photree.albums.cmd_handler.exporter import ExportFailure
from photree.common.formatting import format_dry_run, indent
from photree.common.fs import display_path


def batch_export_summary(exported: int, failed: int, *, dry_run: bool = False) -> str:
    """Return the closing line for a batch export, preceded by a blank line."""
    return (
        format_dry_run(
            f"\n{exported} album(s) would be exported, {failed} failed.",
            dry_run=True,
        )
        if dry_run
        else f"\nDone. {exported} album(s) exported, {failed} failed."
    )


def format_export_failure_reason(failure: ExportFailure, cwd: Path) -> str:
    """
    Word why an album of a batch export failed (plain text).

    An album refused because others export to the same directory names them
    and the directory, relative to *cwd*.
    """
    match failure:
        case ExportFailure(target_dir=Path() as target, colliding_albums=others):
            shown = ", ".join(f'"{display_path(other, cwd)}"' for other in others)
            return (
                f"not exported: {shown} would export to the same directory,"
                f" {display_path(target, cwd)}; rename one of them"
            )
        case _:
            return failure.reason


def format_batch_export_failures(failed: Sequence[ExportFailure], cwd: Path) -> str:
    """
    Plain text (print with ``markup=False``) listing each failed album and why.

    Followed by the ``album export`` command that reruns each one alone.
    """
    return "\n".join(
        [
            "\nFailed albums:",
            *(
                indent(
                    f"{display_path(failure.album_dir, cwd)}\n"
                    f"{indent(format_export_failure_reason(failure, cwd))}",
                )
                for failure in failed
            ),
            "\nTo investigate failures:",
            *(
                indent(
                    "photree album export --album-dir "
                    f'"{display_path(failure.album_dir, cwd)}"',
                )
                for failure in failed
            ),
        ],
    )
