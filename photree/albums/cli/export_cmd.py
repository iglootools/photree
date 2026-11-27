"""The ``photree albums export`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.albums.batchcli.export import (
    resolve_export_settings_or_exit,
    run_batch_export,
)
from photree.albums.cli.app import app
from photree.albums.cli.options import ALBUM_DIR_OPTION
from photree.albums.cmd_handler.exporter import find_export_dirs
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
from photree.clihelpers.usage import mutually_exclusive_error


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
    album_dirs: ALBUM_DIR_OPTION = None,
    share_dir: SHARE_DIR_OPTION = None,
    profile: PROFILE_OPTION = None,
    config: CONFIG_OPTION = None,
    share_layout: SHARE_LAYOUT_OPTION = None,
    album_layout: ALBUM_LAYOUT_OPTION = None,
    link_mode: EXPORT_LINK_MODE_OPTION = None,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """
    Batch export multiple albums to a shared directory.

    Either scan --dir for albums or provide explicit album directories via
    --album-dir (repeatable). The two options are mutually exclusive.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    if base_dir is not None and album_dirs is not None:
        raise mutually_exclusive_error(
            ("--dir", "--album-dir"),
            command="albums export",
        )

    settings = resolve_export_settings_or_exit(
        profile=profile,
        share_dir=share_dir,
        share_layout=share_layout,
        album_layout=album_layout,
        link_mode=link_mode,
        config=config,
        cwd=cwd,
        load=runtime.load_config,
        command="albums export",
    )
    albums = (
        list(album_dirs)
        if album_dirs is not None
        else find_export_dirs(base_dir or cwd)
    )
    run_batch_export(albums, settings, dry_run=dry_run, cwd=cwd)
