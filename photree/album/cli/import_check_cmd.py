"""``photree album import-check`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ...clihelpers.options import CONFIG_OPTION
from ..store.protocol import SELECTION_CSV, SELECTION_DIR
from . import album_app
from .helpers import _run_preflight_checks


@album_app.command("import-check")
def import_check_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help=f"Album directory (with {SELECTION_DIR}/ and/or {SELECTION_CSV}).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    source: Annotated[
        Optional[Path],
        typer.Option(
            "--source",
            "-s",
            help="Image Capture output directory. Overrides config and default.",
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    config: CONFIG_OPTION = None,
) -> None:
    """Check that system prerequisites for import commands are met."""
    _run_preflight_checks(source, config, album_dir=album_dir)
