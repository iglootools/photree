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


def format_batch_export_failures(failed: Sequence[ExportFailure], cwd: Path) -> str:
    """
    Plain text (print with ``markup=False``) listing each failed album and why.

    Followed by the ``album export`` command that reruns each one alone.
    """
    return "\n".join(
        [
            "\nFailed albums:",
            *(
                indent(f"{display_path(album_dir, cwd)}\n{indent(error)}")
                for album_dir, error in failed
            ),
            "\nTo investigate failures:",
            *(
                indent(
                    "photree album export --album-dir "
                    f'"{display_path(album_dir, cwd)}"',
                )
                for album_dir, _ in failed
            ),
        ],
    )
