"""Command handlers for batch album operations.

Each module contains a single handler function + its result dataclass.
These functions orchestrate domain operations, accept ``on_*`` callbacks
for progress notification, and return structured results.

No module in this package imports ``typer``, ``rich``, or ``clihelpers``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BatchFailure:
    """One album that failed, and why.

    The reason is the point: a batch that reports only *which* albums failed
    forces the user to re-run each one individually to learn anything, which
    is the slowest possible way to deliver information the batch already had.
    """

    album_dir: Path
    reason: str
