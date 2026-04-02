"""System prerequisite checks (sips, exiftool)."""

from __future__ import annotations

import shutil


def check_sips_available() -> bool:
    """Check whether the macOS ``sips`` tool is on PATH."""
    return shutil.which("sips") is not None


def check_exiftool_available() -> bool:
    """Check whether ``exiftool`` is on PATH."""
    return shutil.which("exiftool") is not None
