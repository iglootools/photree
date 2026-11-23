"""
System prerequisite check for sips.

A thin album-facing wrapper over :mod:`photree.common.sysdeps`, which owns the
dependency list, purposes, and install hints.
"""

import shutil

from photree.common.sysdeps import SystemDependency, WhichFn, is_available


def check_sips_available(*, which: WhichFn = shutil.which) -> bool:
    """Return whether ``sips`` is on PATH."""
    return is_available(SystemDependency.SIPS, which=which)
