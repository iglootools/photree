"""``photree gallery export`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...album.cli.helpers import format_config_error
from ...album.exporter import batch as _batch
from ...album.exporter import output as _export_output
from ...album.exporter.settings import (
    ExportSettingsError,
    ResolvedExportSettings,
    resolve_export_settings,
    validate_export_settings,
)
from ...album.store.album_discovery import discover_albums
from ...clihelpers.console import err_console
from ...clihelpers.options import (
    ALBUM_LAYOUT_OPTION,
    CONFIG_OPTION,
    EXPORT_LINK_MODE_OPTION,
    PROFILE_OPTION,
    SHARE_DIR_OPTION,
    SHARE_LAYOUT_OPTION,
)
from ...clihelpers.progress import BatchProgressBar
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...common.formatting import indent
from ...common.fs import display_path
from ...config import ConfigError
from ...fsprotocol import ALBUMS_DIR, AlbumShareLayout, LinkMode, ShareDirectoryLayout
from . import gallery_app


@gallery_app.command("export")
def export_cmd(
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
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
            help=(
                "Gallery root directory (or resolved from cwd via "
                ".photree/gallery.yaml). Used when neither --dir nor "
                "--album-dir is given."
            ),
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    share_dir: SHARE_DIR_OPTION = None,
    profile: PROFILE_OPTION = None,
    config: CONFIG_OPTION = None,
    share_layout: SHARE_LAYOUT_OPTION = None,
    album_layout: ALBUM_LAYOUT_OPTION = None,
    link_mode: EXPORT_LINK_MODE_OPTION = None,
) -> None:
    """Batch export the gallery's albums to a shared directory.

    Exports every album of the gallery (--gallery-dir, or the gallery
    containing the current directory). Alternatively, scan --dir for albums
    or provide explicit album directories via --album-dir (repeatable). The
    three options are mutually exclusive.
    """
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
        err_console.print(f"{' and '.join(given)} are mutually exclusive.")
        raise typer.Exit(code=1)

    settings = _resolve_settings_or_exit(
        profile=profile,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config=config,
    )
    albums = _resolve_albums(base_dir, album_dirs, gallery_dir)
    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)
    _export(albums, settings, Path.cwd())


def _resolve_settings_or_exit(
    *,
    profile: str | None,
    share_dir: Path | None,
    share_layout: ShareDirectoryLayout | None,
    album_layout: AlbumShareLayout | None,
    link_mode: LinkMode | None,
    config: str | None,
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
        )
        validate_export_settings(settings)
    except ConfigError as exc:
        err_console.print(format_config_error(exc), markup=False)
        raise typer.Exit(code=2) from exc
    except ExportSettingsError as exc:
        err_console.print(
            _export_output.format_export_settings_error(
                exc, Path.cwd(), "gallery export"
            ),
            markup=False,
        )
        raise typer.Exit(code=1) from exc
    return settings


def _resolve_albums(
    base_dir: Path | None, album_dirs: list[Path] | None, gallery_dir: Path | None
) -> list[Path]:
    """Albums to export: explicit list, a --dir scan, or the whole gallery."""
    match base_dir, album_dirs:
        case _, list() as explicit:
            return explicit
        case Path() as scan_dir, None:
            return _batch.discover_albums(scan_dir)
        case _:
            gallery = resolve_gallery_or_exit(gallery_dir)
            return discover_albums(gallery / ALBUMS_DIR)


def _export(albums: list[Path], settings: ResolvedExportSettings, cwd: Path) -> None:
    with BatchProgressBar(
        total=len(albums), description="Exporting", done_description="export"
    ) as progress:
        result = _batch.run_batch_export(
            album_dirs=albums,
            share_dir=settings.share_dir,
            share_layout=settings.share_layout,
            album_layout=settings.album_layout,
            link_mode=settings.link_mode,
            on_exporting=progress.on_start,
            on_exported=lambda name: progress.on_end(name, success=True),
            on_error=lambda name, error: progress.on_end(
                name, success=False, error_labels=(error,)
            ),
        )

    typer.echo(_export_output.batch_export_summary(result.exported, len(result.failed)))
    if result.failed:
        err_console.print(
            "\n".join(
                [
                    "\nFailed albums:",
                    *(
                        indent(f"{display_path(album_dir, cwd)}: {error}")
                        for album_dir, error in result.failed
                    ),
                ]
            ),
            markup=False,
        )
        raise typer.Exit(code=1)
