"""Shared helpers for album CLI commands."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.sysdeps import import_deps
from ...common.fs import display_path
from ...common.sysdeps import check_system_dependencies
from ...config import ConfigError
from ..importer import output as importer_output
from ..importer.preflight import resolve_image_capture_dir, run_preflight
from ..store.media_sources_discovery import MediaSourceConflictError


def format_config_error(exc: ConfigError) -> str:
    """Plain text (print with ``markup=False``: TOML tables look like markup)."""
    return (
        f"Invalid configuration: {exc}\n"
        "Fix the config file, or pass --config to use another one."
    )


def format_media_source_conflict(exc: MediaSourceConflictError, cwd: Path) -> str:
    """Describe an iOS/std media source name clash, with a fix suggestion."""
    album = display_path(exc.album_dir, cwd)
    names = ", ".join(exc.names)
    return (
        f"{album} has both ios-<name>/ and std-<name>/ archives for: {names}.\n"
        "Both would share the same browsable directories and media IDs. "
        "Rename one of the two archive directories (and its browsable "
        "directories) so every media source name is unique."
    )


@contextmanager
def exit_on_media_source_conflict(cwd: Path) -> Iterator[None]:
    """Report a :class:`MediaSourceConflictError` and exit 1 instead of a traceback."""
    try:
        yield
    except MediaSourceConflictError as exc:
        # markup=False: album names may contain "[private]", which Rich
        # would otherwise swallow as a style tag.
        err_console.print(format_media_source_conflict(exc, cwd), markup=False)
        raise typer.Exit(code=1) from exc


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
        err_console.print(format_config_error(exc), markup=False)
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
    console.print(importer_output.format_preflight_checks(result, cwd=Path.cwd()))

    if not result.success:
        troubleshoot = importer_output.format_preflight_troubleshoot(
            result, cwd=Path.cwd()
        )
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
