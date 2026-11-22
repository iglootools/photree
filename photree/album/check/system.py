"""System prerequisite checks (sips, exiftool).

Thin album-facing wrappers over :mod:`photree.common.sysdeps`, which owns the
dependency list, purposes, and install hints.
"""

import shutil

from photree.common.sysdeps import SystemDependency, WhichFn, is_available


def check_sips_available(*, which: WhichFn = shutil.which) -> bool:
    return is_available(SystemDependency.SIPS, which=which)


def check_exiftool_available(*, which: WhichFn = shutil.which) -> bool:
    return is_available(SystemDependency.EXIFTOOL, which=which)
