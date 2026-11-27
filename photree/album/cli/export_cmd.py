"""The ``photree album export`` command."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from photree.album.cli.app import app
from photree.album.exporter import output as export_output, single as album_export
from photree.album.exporter.settings import (
    ExportSettingsError,
    ResolvedExportSettings,
    is_usage_error,
    resolve_export_settings,
    validate_export_settings,
)
from photree.album.exporter.single import (
    compute_target_dir as export_compute_target_dir,
)
from photree.clihelpers.config_errors import format_config_error
from photree.clihelpers.console import err_console
from photree.clihelpers.options import (
    ALBUM_LAYOUT_OPTION,
    CONFIG_OPTION,
    DRY_RUN_OPTION,
    EXPORT_LINK_MODE_OPTION,
    PROFILE_OPTION,
    SHARE_DIR_OPTION,
    SHARE_LAYOUT_OPTION,
)
from photree.clihelpers.runtime import runtime_of
from photree.common.formatting import markup_escape
from photree.common.fs import display_path
from photree.config import ConfigError, PhotreeConfig
from photree.dates import DatePrefixError
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout


@app.command("export")
def export_cmd(
    ctx: typer.Context,
    *,
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
    ] = Path(),
    share_dir: SHARE_DIR_OPTION = None,
    profile: PROFILE_OPTION = None,
    config: CONFIG_OPTION = None,
    share_layout: SHARE_LAYOUT_OPTION = None,
    album_layout: ALBUM_LAYOUT_OPTION = None,
    link_mode: EXPORT_LINK_MODE_OPTION = None,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """
    Export a single album to a shared directory.

    Creates a subdirectory named after the album inside --share-dir.
    Re-exporting mirrors the album: files an earlier export left there that the
    album no longer has are removed.

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
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    settings = _resolve_settings_or_exit(
        profile=profile,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config=config,
        cwd=cwd,
        load=runtime.load_config,
    )
    target_dir = _target_dir_or_exit(album_dir, settings, cwd)
    result = _export_or_exit(album_dir, target_dir, settings, cwd, dry_run=dry_run)
    typer.echo(
        export_output.export_summary(
            result.album_name,
            result.album_type,
            files_copied=result.files_copied,
            files_removed=result.files_removed,
            target=display_path(target_dir, cwd),
            dry_run=dry_run,
        ),
    )


def _resolve_settings_or_exit(
    *,
    profile: str | None,
    share_dir: Path | None,
    share_layout: ShareDirectoryLayout | None,
    album_layout: AlbumShareLayout | None,
    link_mode: LinkMode | None,
    config: Path | None,
    cwd: Path,
    load: Callable[[Path | None], PhotreeConfig],
) -> ResolvedExportSettings:
    """
    Resolve and validate the export settings, or print why not and exit.

    A bad config file or flag exits 2; a share dir without its sentinel, 1.
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
        # Configuration errors exit 2, like every other command reading config.
        err_console.print(format_config_error(exc), markup=False)
        raise typer.Exit(code=2) from exc
    except ExportSettingsError as exc:
        err_console.print(
            export_output.format_export_settings_error(exc, cwd, "album export"),
            markup=False,
        )
        raise typer.Exit(code=2 if is_usage_error(exc.kind) else 1) from exc
    return settings


def _target_dir_or_exit(
    album_dir: Path,
    settings: ResolvedExportSettings,
    cwd: Path,
) -> Path:
    """Return where the share layout places the album, or exit 1 with a hint."""
    try:
        return export_compute_target_dir(
            settings.share_dir,
            album_dir.name,
            settings.share_layout,
        )
    except DatePrefixError as exc:
        err_console.print(
            f"Cannot place album under the '{settings.share_layout}' share"
            f" layout: {markup_escape(exc)}.",
        )
        album_display = markup_escape(display_path(album_dir, cwd))
        err_console.print(
            "Rename the album to follow the naming convention, or run"
            f" 'photree album export --album-dir \"{album_display}\"'"
            " with '--share-layout flat'.",
        )
        raise typer.Exit(code=1) from exc


def _export_or_exit(
    album_dir: Path,
    target_dir: Path,
    settings: ResolvedExportSettings,
    cwd: Path,
    *,
    dry_run: bool,
) -> album_export.ExportResult:
    """Export the album to *target_dir*, or exit 1 on a filesystem error."""
    try:
        return album_export.export_album(
            album_dir,
            target_dir,
            album_layout=settings.album_layout,
            link_mode=settings.link_mode,
            dry_run=dry_run,
        )
    except OSError as exc:
        # A full or read-only share, or one that refuses links (exFAT, SMB).
        err_console.print(
            export_output.format_export_failure(album_dir, exc, cwd, settings),
            markup=False,
        )
        raise typer.Exit(code=1) from exc
