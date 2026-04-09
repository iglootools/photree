"""macOS ``sips`` wrapper — image conversion, resizing, and metadata queries.

All functions build argument lists rather than shell strings to avoid quoting
issues.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def convert_to_jpeg(src: Path, dst: Path) -> None:
    """Convert *src* to JPEG via ``sips``, writing to *dst*.

    Preserves EXIF metadata. Works with HEIC, DNG, JPEG, PNG, etc.
    """
    subprocess.run(
        ["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)],
        check=True,
        capture_output=True,
    )


def resize_to_jpeg(src: Path, dst: Path, *, max_dimension: int) -> None:
    """Convert *src* to a resized JPEG (longest edge ≤ *max_dimension*).

    Uses ``--resampleHeightWidthMax`` so the aspect ratio is preserved.
    """
    subprocess.run(
        [
            "sips",
            "-s",
            "format",
            "jpeg",
            "--resampleHeightWidthMax",
            str(max_dimension),
            str(src),
            "--out",
            str(dst),
        ],
        check=True,
        capture_output=True,
    )


def get_dimensions(path: Path) -> tuple[int, int]:
    """Return ``(width, height)`` of an image file via ``sips``."""
    result = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    width = height = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            width = int(line.split(":")[1].strip())
        elif line.startswith("pixelHeight:"):
            height = int(line.split(":")[1].strip())
    return (width, height)
