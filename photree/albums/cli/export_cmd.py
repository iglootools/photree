"""``photree albums export`` command."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from ...album.exporter import batch
from ...album.exporter import output as export_output
from ...album.exporter.batch import BatchExportResult
from ...album.exporter.settings import (
    ExportSettingsError,
    ResolvedExportSettings,
    resolve_export_settings,
    validate_export_settings,
)
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
from ...clihelpers.progress import BatchProgressBar
from ...common.formatting import indent
from ...common.fs import display_path
from ...config import ConfigError
from ...foundation.linking import LinkMode
from ...foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout
from . import AlbumDirOption, albums_app


@albums_app.command("export")
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
    if base_dir is not None and album_dirs is not None:
        err_console.print(
            "--dir and --album-dir are mutually exclusive.\n"
            "Run 'photree albums export --help' for usage."
        )
        raise typer.Exit(code=1)

    settings = _resolve_settings_or_exit(
        profile=profile,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config=config,
    )
    cwd = Path.cwd()
    scan_dir = None if album_dirs is not None else (base_dir or cwd)
    albums = (
        list(album_dirs)
        if album_dirs is not None
        else batch.discover_albums(scan_dir or cwd)
    )
    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    result = _export(albums, scan_dir, album_dirs, settings)
    typer.echo(export_output.batch_export_summary(result.exported, len(result.failed)))
    if result.failed:
        _report_failures(result.failed, cwd)
        raise typer.Exit(code=1)


def _resolve_settings_or_exit(
    *,
    profile: str | None,
    share_dir: Path | None,
    share_layout: ShareDirectoryLayout | None,
    album_layout: AlbumShareLayout | None,
    link_mode: LinkMode | None,
    config: str | None,
) -> ResolvedExportSettings:
    """Resolve and validate export settings; config errors exit 2, others 1."""
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
            export_output.format_export_settings_error(
                exc, Path.cwd(), "albums export"
            ),
            markup=False,
        )
        raise typer.Exit(code=1) from exc
    return settings


def _export(
    albums: list[Path],
    scan_dir: Path | None,
    album_dirs: list[Path] | None,
    settings: ResolvedExportSettings,
) -> BatchExportResult:
    with BatchProgressBar(
        total=len(albums), description="Exporting", done_description="export"
    ) as progress:
        return batch.run_batch_export(
            base_dir=scan_dir,
            album_dirs=album_dirs,
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


def _report_failures(failed: Sequence[tuple[Path, str]], cwd: Path) -> None:
    err_console.print(
        "\n".join(
            [
                "\nFailed albums:",
                *(
                    indent(f"{display_path(album_dir, cwd)}\n{indent(error)}")
                    for album_dir, error in failed
                ),
                "\nTo investigate failures:",
                *(
                    indent(
                        "photree album export --album-dir "
                        f'"{display_path(album_dir, cwd)}"'
                    )
                    for album_dir, _ in failed
                ),
            ]
        ),
        markup=False,
    )
