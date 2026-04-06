"""``photree collections check`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from ...common.fs import display_path
from ...common.formatting import CHECK, CROSS
from ...collection.check import check_all_collections
from ...gallery.cli.ops import resolve_gallery_or_exit
from . import collections_app


@collections_app.command("check")
def check_cmd(
    gallery_dir: Annotated[
        Optional[Path],
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
    """Check all collections in the gallery."""
    cwd = Path.cwd()
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    results = check_all_collections(resolved_gallery)

    if not results:
        typer.echo("No collections found.")
        return

    failed = 0
    for result in results:
        name = display_path(result.collection_dir, cwd)
        if result.success:
            typer.echo(f"{CHECK} {name}")
        else:
            failed += 1
            typer.echo(f"{CROSS} {name}")
            for issue in result.issues:
                typer.echo(f"    {issue.message}")

    typer.echo(f"\n{len(results)} collection(s) checked, {failed} with issues.")
    if failed:
        raise typer.Exit(code=1)
