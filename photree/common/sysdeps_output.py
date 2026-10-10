"""Rendering of system dependency statuses (Rich markup, unindented).

Pure formatting, shared by the CLI gate (``clihelpers.sysdeps``) and by the
domain output layers that fold dependency checks into a wider report (the
import preflight, ``check`` troubleshooting).
"""

from __future__ import annotations

from collections.abc import Iterable

from .formatting import CHECK, CROSS
from .sysdeps import SystemDependency, SystemDependencyStatus, install_hint, purpose


def format_status(status: SystemDependencyStatus) -> str:
    """Format one dependency as a check line (Rich markup)."""
    return (
        f"{CHECK} {status.dependency}"
        if status.available
        else f"{CROSS} {status.dependency} (not found)"
    )


def format_statuses(statuses: Iterable[SystemDependencyStatus]) -> str:
    """Format all dependency check lines, one per line."""
    return "\n".join(format_status(s) for s in statuses)


def format_missing_troubleshoot(missing: Iterable[SystemDependency]) -> str:
    """Format install instructions for each missing dependency."""
    return "\n\n".join(
        f"{dependency}: required for {purpose(dependency)}.\n{install_hint(dependency)}"
        for dependency in missing
    )
