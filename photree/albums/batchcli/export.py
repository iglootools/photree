"""``albums export`` / ``gallery export`` wrapper."""

from collections.abc import Callable
from pathlib import Path

import typer

from photree.album.exporter import output as export_output
from photree.album.exporter.settings import (
    ExportSettingsError,
    ResolvedExportSettings,
    resolve_export_settings,
    validate_export_settings,
)
from photree.albums.cmd_handler import exporter as batch
from photree.albums.output import exporter as batch_export_output
from photree.clihelpers.config_errors import format_config_error
from photree.clihelpers.console import err_console
from photree.clihelpers.progress import BatchProgressBar
from photree.config import ConfigError, PhotreeConfig
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


def resolve_export_settings_or_exit(
    *,
    profile: str | None,
    share_dir: Path | None,
    share_layout: ShareDirectoryLayout | None,
    album_layout: AlbumShareLayout | None,
    link_mode: LinkMode | None,
    config: str | None,
    cwd: Path,
    load: Callable[[str | None], PhotreeConfig],
    command: str,
) -> ResolvedExportSettings:
    """
    Resolve and validate the export settings, or print why not and exit.

    A bad config file exits 2, invalid settings exit 1. *command* is the
    export command running, e.g. ``albums export``, named in the fix hint.
    """
    try:
        settings = resolve_export_settings(
            profile_name=profile,
            share_dir=share_dir,
            share_layout=share_layout,
            album_layout=album_layout,
            link_mode=link_mode,
            config_path=config,
            load=load,
        )
        validate_export_settings(settings)
    except ConfigError as exc:
        err_console.print(format_config_error(exc), markup=False)
        raise typer.Exit(code=2) from exc
    except ExportSettingsError as exc:
        err_console.print(
            export_output.format_export_settings_error(exc, cwd, command),
            markup=False,
        )
        raise typer.Exit(code=1) from exc
    return settings


def run_batch_export(
    albums: list[Path],
    settings: ResolvedExportSettings,
    *,
    dry_run: bool,
    cwd: Path,
) -> None:
    """Export *albums*, print a summary, and exit 1 if any album failed."""
    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    with BatchProgressBar(
        total=len(albums),
        description="Exporting",
        done_description="export",
    ) as progress:
        result = batch.run_batch_export(
            album_dirs=albums,
            share_dir=settings.share_dir,
            share_layout=settings.share_layout,
            album_layout=settings.album_layout,
            link_mode=settings.link_mode,
            dry_run=dry_run,
            on_exporting=progress.on_start,
            on_exported=lambda name: progress.on_end(name, success=True),
            on_error=lambda name, failure: progress.on_end(
                name,
                success=False,
                error_labels=(
                    batch_export_output.format_export_failure_reason(failure, cwd),
                ),
            ),
        )

    typer.echo(
        batch_export_output.batch_export_summary(
            result.exported,
            len(result.failed),
            dry_run=dry_run,
        ),
    )
    if result.failed:
        err_console.print(
            batch_export_output.format_batch_export_failures(result.failed, cwd),
            markup=False,
        )
        raise typer.Exit(code=1)
