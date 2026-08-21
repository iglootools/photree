"""macOS ``sips`` wrapper — image conversion, resizing, and metadata queries.

All functions build argument lists rather than shell strings to avoid quoting
issues.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SipsError(Exception):
    """A ``sips`` invocation exited non-zero.

    ``subprocess`` captures sips' diagnostics on the ``CalledProcessError``'s
    ``stderr`` attribute, which ``str(exc)`` does not print — so the one line
    explaining the failure never reached the user. This carries it in the
    message and as structured data.
    """

    path: Path
    returncode: int
    stderr: str

    def __str__(self) -> str:
        detail = self.stderr.strip() or f"sips exited {self.returncode}"
        return f"{self.path.name}: {detail}"


def _run(args: list[str], *, path: Path) -> subprocess.CompletedProcess[str]:
    """Run a sips command, raising :class:`SipsError` with its stderr on failure."""
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise SipsError(path=path, returncode=result.returncode, stderr=result.stderr)
    return result


def convert_to_jpeg(src: Path, dst: Path) -> None:
    """Convert *src* to JPEG via ``sips``, writing to *dst*.

    Preserves EXIF metadata. Works with HEIC, DNG, JPEG, PNG, etc.
    """
    _run(["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)], path=src)


def resize_to_jpeg(src: Path, dst: Path, *, max_dimension: int) -> None:
    """Convert *src* to a resized JPEG (longest edge ≤ *max_dimension*).

    Uses ``--resampleHeightWidthMax`` so the aspect ratio is preserved.
    """
    _run(
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
        path=src,
    )


def get_dimensions(path: Path) -> tuple[int, int]:
    """Return ``(width, height)`` of an image file via ``sips``."""
    result = _run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)], path=path
    )
    width = height = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            width = int(line.split(":")[1].strip())
        elif line.startswith("pixelHeight:"):
            height = int(line.split(":")[1].strip())
    return (width, height)
