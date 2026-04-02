"""Shared helpers for album CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from ...clihelpers.console import console, err_console
from ...config import ConfigError
from .. import check as album_check
from ..check import output as preflight_output
from ..importer import output as importer_output
from ..importer.preflight import resolve_image_capture_dir, run_preflight


def _check_sips_or_exit() -> None:
    if not album_check.check_sips_available():
        err_console.print(preflight_output.sips_check(False))
        err_console.print(preflight_output.sips_troubleshoot())
        raise typer.Exit(code=1)


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

    result = run_preflight(
        image_capture_dir,
        album_dir=album_dir,
        force=force,
        skip_heic_to_jpeg=skip_heic_to_jpeg,
    )

    typer.echo("Preflight Checks:")
    console.print(importer_output.format_preflight_checks(result))

    if not result.success:
        troubleshoot = importer_output.format_preflight_troubleshoot(result)
        if troubleshoot:
            typer.echo("")
            err_console.print(troubleshoot)
        raise typer.Exit(code=1)

    return image_capture_dir
