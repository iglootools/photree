"""The ``photree gallery export`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.store.album_discovery import discover_gallery_albums
from photree.albums.batchcli.export import (
    resolve_export_settings_or_exit,
    run_batch_export,
)
from photree.albums.cmd_handler.exporter import find_export_dirs
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
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import mutually_exclusive_error
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

    settings = resolve_export_settings_or_exit(
        profile=profile,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config=config,
        cwd=cwd,
        load=runtime.load_config,
        command="gallery export",
    )
    albums = _resolve_albums(base_dir, album_dirs, gallery_dir, cwd=cwd)
    run_batch_export(albums, settings, dry_run=dry_run, cwd=cwd)


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
            return find_export_dirs(scan_dir)
        case _:
            gallery = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
            return discover_gallery_albums(gallery)
