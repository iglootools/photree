"""Shared helpers for album CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.sysdeps import import_deps
from ...common.sysdeps import check_system_dependencies
from ...config import ConfigError
from ..importer import output as importer_output
from ..importer.preflight import resolve_image_capture_dir, run_preflight


def _run_preflight_checks(
    source: Path | None,
    config_path: str | None,
    *,
    album_dir: Path | None = None,
    force: bool = False,
    skip_heic_to_jpeg: bool = False,
) -> Path:
    """Run all preflight checks and resolve the Image Capture directory.

    Prints all check lines first, then troubleshooting for failures at the end.
    """
    try:
        image_capture_dir = resolve_image_capture_dir(source, config_path)
    except ConfigError as exc:
        err_console.print(str(exc))
        raise typer.Exit(code=2) from exc

    # Probing PATH is the CLI layer's job; run_preflight stays pure. The
    # statuses are folded into the preflight result rather than gated
    # separately so a broken setup reports every problem in one pass.
    result = run_preflight(
        image_capture_dir,
        system_deps=check_system_dependencies(
            import_deps(skip_heic_to_jpeg=skip_heic_to_jpeg)
        ),
        album_dir=album_dir,
        force=force,
    )

    typer.echo("Preflight Checks:")
    console.print(importer_output.format_preflight_checks(result))

    if not result.success:
        troubleshoot = importer_output.format_preflight_troubleshoot(result)
        if troubleshoot:
            typer.echo("")
            err_console.print(troubleshoot)
        # Preflight runs before any filesystem mutation, so an all-or-nothing
        # abort here is what keeps a missing binary from failing every album
        # individually, halfway through a batch.
        err_console.print(
            "\nAborted before starting: preflight checks failed. Nothing was imported."
        )
        raise typer.Exit(code=1)

    return image_capture_dir
