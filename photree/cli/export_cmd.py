"""CLI commands for the ``photree export`` sub-app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Annotated, Optional

import typer

from ..config import ConfigError, load_config
from ..exporter import export as album_export
from ..exporter import export_all
from ..exporter import output as export_output
from ..exporter.export import compute_target_dir
from ..fsprotocol import (
    SHARE_SENTINEL,
    AlbumShareLayout,
    LinkMode,
    ShareDirectoryLayout,
    display_path,
)

export_app = typer.Typer(
    name="export",
    help="Export albums to a shared directory.",
    no_args_is_help=True,
)


@dataclass(frozen=True)
class _ResolvedExportSettings:
    share_dir: Path
    share_layout: ShareDirectoryLayout
    album_layout: AlbumShareLayout
    link_mode: LinkMode


def _resolve_export_settings(
    *,
    profile_name: str | None,
    share_dir: Path | None,
    share_layout: ShareDirectoryLayout | None,
    album_layout: AlbumShareLayout | None,
    link_mode: LinkMode | None,
    config_path: str | None,
) -> _ResolvedExportSettings:
    """Resolve export settings: CLI flags > profile > defaults."""
    profile = None
    if profile_name is not None:
        try:
            cfg = load_config(config_path)
        except ConfigError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc

        profile = cfg.exporter.profiles.get(profile_name)
        if profile is None:
            available = ", ".join(sorted(cfg.exporter.profiles)) or "(none)"
            typer.echo(
                f'Unknown profile "{profile_name}". Available profiles: {available}',
                err=True,
            )
            raise typer.Exit(code=1)

    resolved_share_dir = share_dir or (profile.share_dir if profile else None)
    if resolved_share_dir is None:
        typer.echo(
            "No --share-dir specified and no profile selected.",
            err=True,
        )
        raise typer.Exit(code=1)

    resolved_share_layout = (
        share_layout
        or (profile.share_layout if profile else None)
        or ShareDirectoryLayout.FLAT
    )
    resolved_album_layout = (
        album_layout
        or (profile.album_layout if profile else None)
        or AlbumShareLayout.MAIN_JPG
    )
    resolved_link_mode = (
        link_mode or (profile.link_mode if profile else None) or LinkMode.HARDLINK
    )

    return _ResolvedExportSettings(
        share_dir=resolved_share_dir,
        share_layout=resolved_share_layout,
        album_layout=resolved_album_layout,
        link_mode=resolved_link_mode,
    )


def _validate_settings(settings: _ResolvedExportSettings) -> None:
    """Validate resolved settings, checking sentinel and layout constraints."""
    if (
        settings.share_layout == ShareDirectoryLayout.ALBUMS
        and settings.album_layout != AlbumShareLayout.ALL
    ):
        typer.echo(
            f'The "albums" share layout requires --album-layout=all, '
            f"but got --album-layout={settings.album_layout.value}.",
            err=True,
        )
        raise typer.Exit(code=1)

    sentinel = settings.share_dir / SHARE_SENTINEL
    if not sentinel.exists():
        indent = " " * 2
        typer.echo(
            dedent(f"""\
                Share directory does not contain a {SHARE_SENTINEL} sentinel file: \
                {settings.share_dir}

                To initialize a share directory, ensure the volume is mounted
                and create the sentinel file:
                {indent}touch {sentinel}"""),
            err=True,
        )
        raise typer.Exit(code=1)


@export_app.command("album")
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
    share_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--share-dir",
            "-s",
            help="Base directory to export into (a subdirectory with the album name is created).",
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile",
            "-p",
            help="Exporter profile name from config.",
        ),
    ] = None,
    config: Annotated[
        Optional[str],
        typer.Option(
            "--config",
            "-c",
            help="Path to config file.",
        ),
    ] = None,
    share_layout: Annotated[
        Optional[ShareDirectoryLayout],
        typer.Option(
            "--share-layout",
            help="Share layout: flat (default) or albums.",
        ),
    ] = None,
    album_layout: Annotated[
        Optional[AlbumShareLayout],
        typer.Option(
            "--album-layout",
            help="Export layout: main-jpg (default), main, or all.",
        ),
    ] = None,
    link_mode: Annotated[
        Optional[LinkMode],
        typer.Option(
            "--link-mode",
            help="How to create main files in all layout: hardlink (default), symlink, or copy.",
        ),
    ] = None,
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
    settings = _resolve_export_settings(
        profile_name=profile,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config_path=config,
    )
    _validate_settings(settings)

    target_dir = compute_target_dir(
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
            result.album_name, result.files_copied, result.album_type.value
        )
    )


@export_app.command("album-all")
def export_all_cmd(
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
    album_dirs: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to export (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    share_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--share-dir",
            "-s",
            help="Base directory to export into (subdirectories with album names are created).",
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    profile: Annotated[
        Optional[str],
        typer.Option(
            "--profile",
            "-p",
            help="Exporter profile name from config.",
        ),
    ] = None,
    config: Annotated[
        Optional[str],
        typer.Option(
            "--config",
            "-c",
            help="Path to config file.",
        ),
    ] = None,
    share_layout: Annotated[
        Optional[ShareDirectoryLayout],
        typer.Option(
            "--share-layout",
            help="Share layout: flat (default) or albums.",
        ),
    ] = None,
    album_layout: Annotated[
        Optional[AlbumShareLayout],
        typer.Option(
            "--album-layout",
            help="Export layout: main-jpg (default), main, or all.",
        ),
    ] = None,
    link_mode: Annotated[
        Optional[LinkMode],
        typer.Option(
            "--link-mode",
            help="How to create main files in all layout: hardlink (default), symlink, or copy.",
        ),
    ] = None,
) -> None:
    """Batch export multiple albums to a shared directory.

    Either scan --dir for albums or provide explicit album directories via
    --album-dir (repeatable). The two options are mutually exclusive.
    """
    from .progress import BatchProgressBar

    cwd = Path.cwd()

    if base_dir is not None and album_dirs is not None:
        typer.echo("--dir and --album-dir are mutually exclusive.", err=True)
        raise typer.Exit(code=1)

    settings = _resolve_export_settings(
        profile_name=profile,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config_path=config,
    )
    _validate_settings(settings)

    resolved_base = (
        None
        if album_dirs is not None
        else (base_dir if base_dir is not None else Path(".").resolve())
    )

    # Determine album count for progress bar
    albums = (
        list(album_dirs)
        if album_dirs is not None
        else export_all.discover_albums(resolved_base)  # type: ignore[arg-type]
    )

    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    progress = BatchProgressBar(
        total=len(albums), description="Exporting", done_description="export"
    )

    result = export_all.run_batch_export(
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
    progress.stop()

    typer.echo(export_output.batch_export_summary(result.exported, len(result.failed)))

    if result.failed:
        typer.echo("\nFailed albums:", err=True)
        for album_dir_path, error in result.failed:
            typer.echo(f"  {display_path(album_dir_path, cwd)}: {error}", err=True)
        raise typer.Exit(code=1)
