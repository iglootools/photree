"""The ``photree album import-check`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.cli.app import app
from photree.album.cli.import_preflight import run_import_preflight
from photree.clihelpers.options import CONFIG_OPTION
from photree.clihelpers.paths import expand_user_path
from photree.clihelpers.runtime import runtime_of


@app.command("import-check")
def import_check_cmd(
    ctx: typer.Context,
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory (with to-import-{ios,std}-<name> staging dirs).",
            file_okay=False,
            callback=expand_user_path(exists=True),
        ),
    ] = Path(),
    source: Annotated[
        Path | None,
        typer.Option(
            "--source",
            "-s",
            help="Image Capture output directory. Overrides config and default.",
            file_okay=False,
            callback=expand_user_path(),
        ),
    ] = None,
    config: CONFIG_OPTION = None,
) -> None:
    """Check that system prerequisites for import commands are met."""
    run_import_preflight(source, config, album_dir=album_dir, runtime=runtime_of(ctx))
