"""CLI gate for external binary (system dependency) requirements.

Commands that shell out to ``sips`` or ``exiftool`` call
:func:`require_system_deps` before doing any work. Probing up front turns
"every album failed for the same reason, halfway through" into a single
actionable message printed before the first file is touched.
"""

from __future__ import annotations

from collections.abc import Iterable

import typer

from ..common.formatting import CHECK, CROSS
from ..common.sysdeps import (
    SystemDependency,
    SystemDependencyStatus,
    check_system_dependencies,
    install_hint,
    missing_dependencies,
    purpose,
)
from .console import console, err_console

# Requirement sets, named so commands declare intent rather than a binary list.
# Every command's requirement is declared here and nowhere else, so adding a
# binary cannot leave one caller behind.
EXIF_DEPS: tuple[SystemDependency, ...] = (SystemDependency.EXIFTOOL,)
FACE_DETECTION_DEPS: tuple[SystemDependency, ...] = (SystemDependency.SIPS,)


def import_deps(*, skip_heic_to_jpeg: bool = False) -> tuple[SystemDependency, ...]:
    """External binaries an import needs.

    ``exiftool`` is always required: import ends with a derived-data refresh
    that populates the EXIF timestamp cache. ``sips`` is only needed for the
    HEIC/DNG-to-JPEG conversion that ``--skip-heic-to-jpeg`` opts out of —
    a flag only the album-level import commands offer.
    """
    return (
        EXIF_DEPS
        if skip_heic_to_jpeg
        else (SystemDependency.SIPS, SystemDependency.EXIFTOOL)
    )


def refresh_deps() -> tuple[SystemDependency, ...]:
    """External binaries a derived-data refresh needs."""
    return import_deps()


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


def require_system_deps(
    dependencies: Iterable[SystemDependency],
    *,
    header: str | None = "System Checks:",
) -> tuple[SystemDependencyStatus, ...]:
    """Print dependency check lines, exiting before any work if one is missing.

    Pass ``header=None`` when the caller already printed a section header
    (e.g. the import preflight block, which renders its own checks alongside).
    """
    statuses = check_system_dependencies(dependencies)
    if header is not None:
        typer.echo(header)
    console.print(format_statuses(statuses))

    missing = missing_dependencies(statuses)
    if missing:
        typer.echo("")
        err_console.print(format_missing_troubleshoot(missing))
        err_console.print(
            "\nAborted before starting: install the missing system dependencies "
            "above and re-run. Nothing was modified.\n"
            "Run 'photree check system' to re-verify."
        )
        raise typer.Exit(code=1)

    return statuses
