"""``photree album export`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.config_errors import format_config_error
from ...clihelpers.console import err_console
from ...clihelpers.options import (
    ALBUM_LAYOUT_OPTION,
    CONFIG_OPTION,
    EXPORT_LINK_MODE_OPTION,
    PROFILE_OPTION,
    SHARE_DIR_OPTION,
    SHARE_LAYOUT_OPTION,
)
from ...common.formatting import markup_escape
from ...common.fs import display_path
from ...config import ConfigError
from ...dates import DatePrefixError
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

    Directories without a recognizable media source are copied in full
    regardless of --album-layout.

    For albums with media sources (iOS or std):

    --album-layout=browsable-jpg (default): Copies {name}-jpg/ and {name}-vid/
    (most compatible formats).

    --album-layout=browsable: Copies {name}-img/, {name}-jpg/, and {name}-vid/.

    --album-layout=all: Copies archival directories (orig-*, edit-*) and
    {name}-jpg/ as-is, then recreates {name}-img/ and {name}-vid/ using
    --link-mode.

    --album-layout=archive: Copies only the archive (orig-*, edit-*) plus
    .photree/ metadata (excluding the derived cache/). Browsable/JPEG dirs are
    dropped — regenerable via 'photree albums refresh'. Space-efficient for
    backups to destinations without hardlink/symlink support (e.g. MEGA).
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
    except ConfigError as exc:
        # Configuration errors exit 2, like every other command reading config.
        err_console.print(format_config_error(exc), markup=False)
        raise typer.Exit(code=2) from exc
    except ExportSettingsError as exc:
        err_console.print(
            export_output.format_export_settings_error(exc, Path.cwd(), "album export"),
            markup=False,
        )
        raise typer.Exit(code=1) from exc

    try:
        target_dir = export_compute_target_dir(
            settings.share_dir, album_dir.name, settings.share_layout
        )
    except DatePrefixError as exc:
        err_console.print(
            f"Cannot place album under the '{settings.share_layout}' share"
            f" layout: {markup_escape(exc)}."
        )
        album_display = markup_escape(display_path(album_dir, Path.cwd()))
        err_console.print(
            "Rename the album to follow the naming convention, or run"
            f" 'photree album export --album-dir \"{album_display}\"'"
            " with '--share-layout flat'."
        )
        raise typer.Exit(code=1) from exc

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
