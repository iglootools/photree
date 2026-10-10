"""Rendering shared by every batch operation.

Domain-specific rendering belongs with its domain (``album/check/output.py``,
``album/fix/output.py``, …). What lives here is the part that is the same
whatever the operation: how a failed item and its follow-up command read.

Both helpers return Rich markup with user text (paths, reasons) escaped, so
an album tagged ``[private]`` is printed as-is instead of being swallowed as
a markup tag.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import typer

from ...clihelpers.console import err_console
from ...common.formatting import indent, markup_escape
from ...common.fs import display_path
from ..cmd_handler import BatchFailure


def batch_failures_report(failures: Iterable[BatchFailure], base: Path) -> str:
    """Format each failed album with the reason it failed."""
    return "\n".join(
        [
            "\nFailed albums:",
            *(
                indent(f"{markup_escape(display_path(f.album_dir, base))}\n")
                + indent(markup_escape(f.reason), 2)
                for f in failures
            ),
        ]
    )


def investigate_commands(
    command: str,
    albums: Iterable[Path],
    base: Path,
    *,
    extra_flags: str = "",
) -> str:
    """Copy-pasteable single-album commands for reproducing each failure.

    *command* is the single-album verb (``check``, ``fix``, ``refresh``, …).
    Paths are relative to *base* so the suggestion runs as printed.
    """
    return "\n".join(
        [
            "\nTo investigate failures:",
            *(
                indent(
                    markup_escape(
                        f"photree album {command} --album-dir "
                        f'"{display_path(album_dir, base)}"{extra_flags}'
                    )
                )
                for album_dir in albums
            ),
        ]
    )


def album_reports_block(reports: Iterable[tuple[str, str]]) -> str:
    """Per-album detail blocks emitted by the fix operations."""
    return "\n".join(f"{name}:\n{report}" for name, report in reports)


def exit_with_failures(
    failures: Sequence[BatchFailure],
    command: str,
    base: Path,
    *,
    extra_flags: str = "",
) -> None:
    """Print each failure with its reason and a retry command, then exit 1.

    Does nothing when there are no failures.
    """
    if failures:
        err_console.print(batch_failures_report(failures, base))
        err_console.print(
            investigate_commands(
                command, [f.album_dir for f in failures], base, extra_flags=extra_flags
            )
        )
        raise typer.Exit(code=1)


def exit_if_no_albums(
    albums: Sequence[Path],
    display_base: Path | None,
    *,
    noun: str = "album",
) -> None:
    """Exit 0 ("nothing to do") on an empty batch, else announce its size."""
    if not albums:
        typer.echo(f"\nNo {noun}s found.")
        raise typer.Exit(code=0)
    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} {noun}(s).\n")
