"""``photree album export`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.options import (
    ALBUM_LAYOUT_OPTION,
    CONFIG_OPTION,
    EXPORT_LINK_MODE_OPTION,
    PROFILE_OPTION,
    SHARE_DIR_OPTION,
    SHARE_LAYOUT_OPTION,
)
from ...config import ConfigError
from ..exporter import output as export_output
from ..exporter import single as album_export
from ..exporter.settings import (
    ExportSettingsError,
    resolve_export_settings,
    validate_export_settings,
)
from ..exporter.single import compute_target_dir as export_compute_target_dir
from . import album_app


@album_app.command("export")
def export_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to export.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    share_dir: SHARE_DIR_OPTION = None,
    profile: PROFILE_OPTION = None,
    config: CONFIG_OPTION = None,
    share_layout: SHARE_LAYOUT_OPTION = None,
    album_layout: ALBUM_LAYOUT_OPTION = None,
    link_mode: EXPORT_LINK_MODE_OPTION = None,
) -> None:
    """Export a single album to a shared directory.

    Creates a subdirectory named after the album inside --share-dir.

    For non-iOS albums, all files are copied regardless of --album-layout.

    For iOS albums:

    --album-layout=main-jpg (default): Copies main-jpg/ and main-vid/
    (most compatible formats).

    --album-layout=main: Copies main-img/, main-jpg/, and main-vid/.

    --album-layout=all: Copies archival directories (orig-*, edit-*) and
    main-jpg/ as-is, then recreates main-img/ and main-vid/ using --link-mode.
    """
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

    target_dir = export_compute_target_dir(
        settings.share_dir, album_dir.name, settings.share_layout
    )

    result = album_export.export_album(
        album_dir,
        target_dir,
        album_layout=settings.album_layout,
        link_mode=settings.link_mode,
    )

    typer.echo(
        export_output.export_summary(
            result.album_name, result.files_copied, result.album_type
        )
    )
