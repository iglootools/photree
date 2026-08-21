"""System prerequisite checks (sips, exiftool).

Thin album-facing wrappers over :mod:`photree.common.sysdeps`, which owns the
dependency list, purposes, and install hints.
"""

from __future__ import annotations

from ...common.sysdeps import SystemDependency, is_available


def check_sips_available() -> bool:
    """Check whether the macOS ``sips`` tool is on PATH."""
    return is_available(SystemDependency.SIPS)


def check_exiftool_available() -> bool:
    """Check whether ``exiftool`` is on PATH."""
    return is_available(SystemDependency.EXIFTOOL)
