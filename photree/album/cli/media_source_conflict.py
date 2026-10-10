"""Reporting of iOS/std media source name clashes in album commands.

Public to the other CLI layers: the entry point (``photree.cli``) renders the
same message when the error escapes a command.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer

from ...clihelpers.console import err_console
from ...common.fs import display_path
from ..store.media_sources_discovery import MediaSourceConflictError


def format_media_source_conflict(exc: MediaSourceConflictError, cwd: Path) -> str:
    """Describe an iOS/std media source name clash, with a fix suggestion."""
    album = display_path(exc.album_dir, cwd)
    names = ", ".join(exc.names)
    return (
        f"{album} has both ios-<name>/ and std-<name>/ archives for: {names}.\n"
        "Both would share the same browsable directories and media IDs. "
        "Rename one of the two archive directories (and its browsable "
        "directories) so every media source name is unique."
    )


@contextmanager
def exit_on_media_source_conflict(cwd: Path) -> Iterator[None]:
    """Report a :class:`MediaSourceConflictError` and exit 1 instead of a traceback."""
    try:
        yield
    except MediaSourceConflictError as exc:
        # markup=False: album names may contain "[private]", which Rich
        # would otherwise swallow as a style tag.
        err_console.print(format_media_source_conflict(exc, cwd), markup=False)
        raise typer.Exit(code=1) from exc
