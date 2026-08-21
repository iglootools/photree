"""Rendering shared by every batch operation.

Domain-specific rendering belongs with its domain (``album/check/output.py``,
``album/fix/output.py``, …). What lives here is the part that is the same
whatever the operation: how a failed item and its follow-up command read.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ....common.fs import display_path
from ...cmd_handler import BatchFailure


def batch_failures_report(failures: list[BatchFailure], base: Path) -> str:
    """Format each failed album with the reason it failed."""
    return "\n".join(
        [
            "\nFailed albums:",
            *(f"  {display_path(f.album_dir, base)}\n    {f.reason}" for f in failures),
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
                f"  photree album {command} --album-dir "
                f'"{display_path(album_dir, base)}"{extra_flags}'
                for album_dir in albums
            ),
        ]
    )


def album_reports_block(reports: Iterable[tuple[str, str]]) -> str:
    """Per-album detail blocks emitted by the fix operations."""
    return "\n".join(f"{name}:\n{report}" for name, report in reports)
