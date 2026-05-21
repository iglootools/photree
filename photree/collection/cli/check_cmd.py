"""``photree collection check`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console, err_console
from ...common.fs import display_path
from ...common.formatting import CHECK, CROSS
from ...gallery.cli.ops import resolve_gallery_or_exit
from ..check import build_gallery_lookup, check_collection
from . import collection_app


@collection_app.command("check")
def check_cmd(
    collection_dir: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Collection directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """Check collection integrity (member existence, date coverage)."""
    cwd = Path.cwd()
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    lookup = build_gallery_lookup(resolved_gallery)
    result = check_collection(collection_dir, lookup)

    for issue in result.issues:
        console.print(f"  {CROSS} {issue.message}")

    if result.success:
        console.print(f"{CHECK} {display_path(collection_dir, cwd)}")
    else:
        err_console.print(
            f"\n{len(result.issues)} issue(s) found in "
            f"{display_path(collection_dir, cwd)}"
        )
        raise typer.Exit(code=1)
