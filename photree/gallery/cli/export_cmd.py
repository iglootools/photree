"""The ``photree gallery export`` command."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from photree.album.exporter import output as _export_output
from photree.album.exporter.settings import (
    ExportSettingsError,
    ResolvedExportSettings,
    resolve_export_settings,
    validate_export_settings,
)
from photree.album.store.album_discovery import discover_gallery_albums
from photree.albums.cmd_handler import exporter as _batch
from photree.albums.output import exporter as _batch_export_output
from photree.clihelpers.config_errors import format_config_error
from photree.clihelpers.console import err_console
from photree.clihelpers.options import (
    ALBUM_LAYOUT_OPTION,
    CONFIG_OPTION,
    DRY_RUN_OPTION,
    EXPORT_LINK_MODE_OPTION,
    GALLERY_DIR_OPTION,
    PROFILE_OPTION,
    SHARE_DIR_OPTION,
    SHARE_LAYOUT_OPTION,
)
from photree.clihelpers.progress import BatchProgressBar
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import mutually_exclusive_error
from photree.config import ConfigError, PhotreeConfig
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout
from photree.gallery.cli.app import app


@app.command("export")
def export_cmd(
    ctx: typer.Context,
    *,
    base_dir: Annotated[
        Path | None,
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to scan for albums.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    album_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to export (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    gallery_dir: GALLERY_DIR_OPTION = None,
    share_dir: SHARE_DIR_OPTION = None,
    profile: PROFILE_OPTION = None,
    config: CONFIG_OPTION = None,
    share_layout: SHARE_LAYOUT_OPTION = None,
    album_layout: ALBUM_LAYOUT_OPTION = None,
    link_mode: EXPORT_LINK_MODE_OPTION = None,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """
    Batch export the gallery's albums to a shared directory.

    Exports every album of the gallery (--gallery-dir, or the gallery
    containing the current directory). Alternatively, scan --dir for albums
    or provide explicit album directories via --album-dir (repeatable). The
    three options are mutually exclusive.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    given = [
        flag
        for flag, value in (
            ("--dir", base_dir),
            ("--album-dir", album_dirs),
            ("--gallery-dir", gallery_dir),
        )
        if value is not None
    ]
    if len(given) > 1:
        raise mutually_exclusive_error(given)

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
    albums = _resolve_albums(base_dir, album_dirs, gallery_dir, cwd=cwd)
    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)
    _export(albums, settings, cwd, dry_run=dry_run)


def _resolve_settings_or_exit(
    *,
    profile: str | None,
    share_dir: Path | None,
    share_layout: ShareDirectoryLayout | None,
    album_layout: AlbumShareLayout | None,
    link_mode: LinkMode | None,
    config: str | None,
    cwd: Path,
    load: Callable[[str | None], PhotreeConfig],
) -> ResolvedExportSettings:
    """Resolve and validate export settings; a bad config file exits 2."""
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
            _export_output.format_export_settings_error(exc, cwd, "gallery export"),
            markup=False,
        )
        raise typer.Exit(code=1) from exc
    return settings


def _resolve_albums(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    gallery_dir: Path | None,
    *,
    cwd: Path,
) -> list[Path]:
    """Albums to export: explicit list, a --dir scan, or the whole gallery."""
    match base_dir, album_dirs:
        case _, list() as explicit:
            return explicit
        case Path() as scan_dir, None:
            return _batch.find_export_dirs(scan_dir)
        case _:
            gallery = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
            return discover_gallery_albums(gallery)


def _export(
    albums: list[Path],
    settings: ResolvedExportSettings,
    cwd: Path,
    *,
    dry_run: bool,
) -> None:
    with BatchProgressBar(
        total=len(albums),
        description="Exporting",
        done_description="export",
    ) as progress:
        result = _batch.run_batch_export(
            album_dirs=albums,
            share_dir=settings.share_dir,
            share_layout=settings.share_layout,
            album_layout=settings.album_layout,
            link_mode=settings.link_mode,
            dry_run=dry_run,
            on_exporting=progress.on_start,
            on_exported=lambda name: progress.on_end(name, success=True),
            on_error=lambda name, error: progress.on_end(
                name,
                success=False,
                error_labels=(error,),
            ),
        )

    typer.echo(
        _batch_export_output.batch_export_summary(
            result.exported,
            len(result.failed),
            dry_run=dry_run,
        ),
    )
    if result.failed:
        err_console.print(
            _batch_export_output.format_batch_export_failures(result.failed, cwd),
            markup=False,
        )
        raise typer.Exit(code=1)
