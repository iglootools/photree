"""Formatting for batch failures — one album, one reason."""

from __future__ import annotations

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
