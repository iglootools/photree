"""Import preflight shared by the album and albums import commands.

Public to the ``albums`` CLI (``albums import``, ``albums import-check``):
both scopes run the same checks and abort the same way.
"""

from pathlib import Path

import typer

from photree.album.importer import output as importer_output
from photree.album.importer.preflight import resolve_image_capture_dir, run_preflight
from photree.clihelpers.config_errors import format_config_error
from photree.clihelpers.console import console, err_console
from photree.clihelpers.runtime import Runtime
from photree.clihelpers.sysdeps import import_deps
from photree.common.sysdeps import check_system_dependencies
from photree.config import ConfigError


def run_import_preflight(
    source: Path | None,
    config_path: str | None,
    *,
    album_dir: Path | None = None,
    force: bool = False,
    skip_heic_to_jpeg: bool = False,
    runtime: Runtime,
) -> Path:
    """Prints all check lines first, then troubleshooting for failures at the end.

    Reads the machine (binaries, home, config file, working directory) only
    through *runtime*.
    """
    cwd = runtime.cwd()
    try:
        image_capture_dir = resolve_image_capture_dir(
            source, config_path, home=runtime.home, load=runtime.load_config
        )
    except ConfigError as exc:
        err_console.print(format_config_error(exc), markup=False)
        raise typer.Exit(code=2) from exc

    # Probing PATH is the CLI layer's job; run_preflight stays pure. The
    # statuses are folded into the preflight result rather than gated
    # separately so a broken setup reports every problem in one pass.
    result = run_preflight(
        image_capture_dir,
        system_deps=check_system_dependencies(
            import_deps(skip_heic_to_jpeg=skip_heic_to_jpeg),
            which=runtime.which,
        ),
        album_dir=album_dir,
        force=force,
    )

    typer.echo("Preflight Checks:")
    console.print(importer_output.format_preflight_checks(result, cwd=cwd))

    if not result.success:
        troubleshoot = importer_output.format_preflight_troubleshoot(result, cwd=cwd)
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
