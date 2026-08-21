"""External binary (system dependency) discovery.

photree shells out to a small set of external binaries. They are probed once,
up front, so a batch operation aborts before touching the filesystem instead of
failing per item halfway through — a missing binary is a property of the
machine, not of the album being processed, so retrying it per item can only
produce the same failure N times.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from textwrap import dedent

# Injected rather than called directly so tests can probe a synthetic PATH.
WhichFn = Callable[[str], str | None]


class SystemDependency(StrEnum):
    """An external binary photree shells out to."""

    SIPS = "sips"
    EXIFTOOL = "exiftool"


_PURPOSE: dict[SystemDependency, str] = {
    SystemDependency.SIPS: (
        "HEIC/DNG-to-JPEG conversion and face detection thumbnails"
    ),
    SystemDependency.EXIFTOOL: "reading and writing EXIF timestamps",
}

_INSTALL_HINT: dict[SystemDependency, str] = {
    SystemDependency.SIPS: dedent("""\
        sips ships with macOS and cannot be installed separately; photree is
        macOS-only today. Commands that offer --skip-heic-to-jpeg can run
        without it."""),
    SystemDependency.EXIFTOOL: dedent("""\
        Install via: brew install exiftool (macOS)
        or apt install libimage-exiftool-perl (Linux)."""),
}


def purpose(dependency: SystemDependency) -> str:
    """Describe what photree uses *dependency* for."""
    return _PURPOSE[dependency]


def install_hint(dependency: SystemDependency) -> str:
    """Return installation instructions for *dependency*."""
    return _INSTALL_HINT[dependency]


@dataclass(frozen=True)
class SystemDependencyStatus:
    """Availability of a single external binary."""

    dependency: SystemDependency
    available: bool


def is_available(
    dependency: SystemDependency,
    *,
    which: WhichFn = shutil.which,
) -> bool:
    """Return whether *dependency* is on PATH."""
    return which(str(dependency)) is not None


def check_system_dependencies(
    dependencies: Iterable[SystemDependency],
    *,
    which: WhichFn = shutil.which,
) -> tuple[SystemDependencyStatus, ...]:
    """Probe *dependencies*, preserving order and dropping duplicates."""
    return tuple(
        SystemDependencyStatus(
            dependency=dependency, available=is_available(dependency, which=which)
        )
        # dict.fromkeys de-duplicates while keeping first-seen order, so a
        # caller can concatenate requirement lists without worrying about
        # printing the same check line twice.
        for dependency in dict.fromkeys(dependencies)
    )


def missing_dependencies(
    statuses: Iterable[SystemDependencyStatus],
) -> tuple[SystemDependency, ...]:
    """Return the dependencies among *statuses* that are not available."""
    return tuple(s.dependency for s in statuses if not s.available)


class MissingSystemDependencyError(Exception):
    """Raised when a required external binary is not on PATH.

    Carries the missing dependencies as structured data so callers (and tests)
    can inspect them without parsing the message.
    """

    def __init__(self, missing: tuple[SystemDependency, ...]) -> None:
        self.missing = missing
        names = ", ".join(str(d) for d in missing)
        super().__init__(f"Required system dependency not found: {names}")


def require(
    dependencies: Iterable[SystemDependency],
    *,
    which: WhichFn = shutil.which,
) -> None:
    """Raise :class:`MissingSystemDependencyError` if any dependency is absent.

    Library-level guard for code paths that are not fronted by the CLI gate in
    :mod:`photree.clihelpers.sysdeps`.
    """
    missing = missing_dependencies(check_system_dependencies(dependencies, which=which))
    if missing:
        raise MissingSystemDependencyError(missing)
