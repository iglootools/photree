"""macOS ``sips`` wrapper — image conversion, resizing, and metadata queries.

All functions build argument lists rather than shell strings to avoid quoting
issues.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class SipsError(OSError):
    """A ``sips`` invocation failed.

    ``subprocess`` captures sips' diagnostics on the ``CalledProcessError``'s
    ``stderr`` attribute, which ``str(exc)`` does not print — so the one line
    explaining the failure never reached the user. This carries it in the
    message and as structured data.

    It subclasses :class:`OSError` so the per-file batch loops (which catch
    ``OSError``) record a sips failure instead of aborting the directory. It
    is a plain class rather than a frozen dataclass: Python assigns
    ``__traceback__`` on exceptions as they propagate (e.g. through a
    ``@contextmanager``), which a frozen dataclass turns into
    ``FrozenInstanceError``.
    """

    def __init__(self, *, path: Path, returncode: int, stderr: str) -> None:
        self.path = path
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(self.__str__())

    def __str__(self) -> str:
        detail = self.stderr.strip() or f"sips exited {self.returncode}"
        return f"{self.path.name}: {detail}"


def _run(args: list[str], *, path: Path) -> subprocess.CompletedProcess[str]:
    """Run a sips command, raising :class:`SipsError` with its stderr on failure."""
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise SipsError(path=path, returncode=result.returncode, stderr=result.stderr)
    return result


def convert_to_jpeg(src: Path, dst: Path) -> None:
    """Convert *src* to JPEG via ``sips``, writing to *dst*.

    Preserves EXIF metadata. Works with HEIC, DNG, JPEG, PNG, etc.
    """
    _run(["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)], path=src)


def convert_to_heic(src: Path, dst: Path) -> None:
    """Convert *src* to HEIC via ``sips``, writing to *dst*."""
    _run(["sips", "-s", "format", "heic", str(src), "--out", str(dst)], path=src)


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
    # The first output line is the file path (which may itself contain ":"),
    # so only the indented "key: value" property lines are parsed.
    props = {
        key.strip(): value.strip()
        for key, sep, value in (
            line.strip().partition(":") for line in result.stdout.splitlines()[1:]
        )
        if sep
    }
    try:
        return (int(props["pixelWidth"]), int(props["pixelHeight"]))
    except (KeyError, ValueError) as exc:
        raise SipsError(
            path=path,
            returncode=result.returncode,
            stderr=f"could not read pixel dimensions from sips output: {exc}",
        ) from exc
