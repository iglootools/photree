"""``photree albums export`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import AlbumDirOption, albums_app
from ...album.exporter import batch, output as export_output
from ...album.exporter.settings import (
    ExportSettingsError,
    resolve_export_settings,
    validate_export_settings,
)
from ...config import ConfigError
from ...common.fs import display_path
from ...clihelpers.options import (
    ALBUM_LAYOUT_OPTION,
    CONFIG_OPTION,
    EXPORT_LINK_MODE_OPTION,
    PROFILE_OPTION,
    SHARE_DIR_OPTION,
    SHARE_LAYOUT_OPTION,
)


@albums_app.command("export")
def export_cmd(
    base_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to scan for albums.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    album_dirs: AlbumDirOption = None,
    share_dir: SHARE_DIR_OPTION = None,
    profile: PROFILE_OPTION = None,
    config: CONFIG_OPTION = None,
    share_layout: SHARE_LAYOUT_OPTION = None,
    album_layout: ALBUM_LAYOUT_OPTION = None,
    link_mode: EXPORT_LINK_MODE_OPTION = None,
) -> None:
    """Batch export multiple albums to a shared directory.

    Either scan --dir for albums or provide explicit album directories via
    --album-dir (repeatable). The two options are mutually exclusive.
    """
    from ...clihelpers.progress import BatchProgressBar

    cwd = Path.cwd()

    if base_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    try:
        settings = resolve_export_settings(
            profile_name=profile,
            share_dir=share_dir,
            share_layout=share_layout,
            album_layout=album_layout,
            link_mode=link_mode,
            config_path=config,
        )
        validate_export_settings(settings)
    except (ExportSettingsError, ConfigError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    resolved_base = (
        None
        if album_dirs is not None
        else (base_dir if base_dir is not None else Path(".").resolve())
    )

    # Determine album count for progress bar
    albums = (
        list(album_dirs)
        if album_dirs is not None
        else batch.discover_albums(resolved_base)  # type: ignore[arg-type]
    )

    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    with BatchProgressBar(
        total=len(albums), description="Exporting", done_description="export"
    ) as progress:
        result = batch.run_batch_export(
            base_dir=resolved_base,
            album_dirs=album_dirs,
            share_dir=settings.share_dir,
            share_layout=settings.share_layout,
            album_layout=settings.album_layout,
            link_mode=settings.link_mode,
            on_exporting=progress.on_start,
            on_exported=lambda name: progress.on_end(name, success=True),
            on_error=lambda name, error: progress.on_end(name, success=False),
        )

    typer.echo(export_output.batch_export_summary(result.exported, len(result.failed)))

    if result.failed:
        typer.echo("\nFailed albums:", err=True)
        for album_dir_path, error in result.failed:
            typer.echo(f"  {display_path(album_dir_path, cwd)}: {error}", err=True)
        raise typer.Exit(code=1)
