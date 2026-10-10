"""CLI gate for external binary (system dependency) requirements.

Commands that shell out to ``sips`` or ``exiftool`` call
:func:`require_system_deps` before doing any work. Probing up front turns
"every album failed for the same reason, halfway through" into a single
actionable message printed before the first file is touched.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from textwrap import dedent

import typer

from ..common.sysdeps import (
    SystemDependency,
    SystemDependencyStatus,
    WhichFn,
    check_system_dependencies,
    missing_dependencies,
)
from ..common.sysdeps_output import format_missing_troubleshoot, format_statuses
from .console import console, err_console

# Requirement sets, named so commands declare intent rather than a binary list.
# Every command's requirement is declared here and nowhere else, so adding a
# binary cannot leave one caller behind.
EXIF_DEPS: tuple[SystemDependency, ...] = (SystemDependency.EXIFTOOL,)
FACE_DETECTION_DEPS: tuple[SystemDependency, ...] = (SystemDependency.SIPS,)
# The check commands need sips for the browsable/JPEG consistency checks.
# exiftool is deliberately absent: EXIF validation is optional there and
# degrades to a "checks skipped" line (see internals.md, System Dependencies).
CHECK_DEPS: tuple[SystemDependency, ...] = (SystemDependency.SIPS,)


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


_ABORT_MESSAGE = dedent("""\
    Aborted before starting: install the missing system dependencies above and \
    re-run. Nothing was modified.
    Run 'photree check system' to re-verify.""")


def require_system_deps(
    dependencies: Iterable[SystemDependency],
    *,
    header: str | None = "System Checks:",
    abort_message: str | None = _ABORT_MESSAGE,
    which: WhichFn = shutil.which,
) -> tuple[SystemDependencyStatus, ...]:
    """Print dependency check lines, exiting before any work if one is missing.

    Pass ``header=None`` when the caller already printed a section header
    (e.g. the import preflight block, which renders its own checks alongside).
    Pass ``abort_message=None`` when the command *is* the diagnostic
    (``check system``), so it does not tell the user to run itself.
    """
    statuses = check_system_dependencies(dependencies, which=which)
    if header is not None:
        typer.echo(header)
    console.print(format_statuses(statuses))

    missing = missing_dependencies(statuses)
    if missing:
        typer.echo("")
        err_console.print(format_missing_troubleshoot(missing))
        if abort_message is not None:
            err_console.print(f"\n{abort_message}")
        raise typer.Exit(code=1)

    return statuses
