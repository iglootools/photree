"""``photree collections check`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...collection.check import CollectionCheckResult, check_all_collections
from ...common.formatting import CHECK, CROSS, indent, markup_escape
from ...common.fs import display_path
from . import collections_app


def _format_result(result: CollectionCheckResult, cwd: Path) -> str:
    """One check line, followed by the indented issues on failure (Rich markup)."""
    name = markup_escape(display_path(result.collection_dir, cwd))
    return (
        f"{CHECK} {name}"
        if result.success
        else "\n".join(
            [
                f"{CROSS} {name}",
                *(indent(markup_escape(i.message), 2) for i in result.issues),
            ]
        )
    )


@collections_app.command("check")
def check_cmd(
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
    """Check all collections in the gallery."""
    cwd = Path.cwd()
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    results = check_all_collections(resolved_gallery)

    if not results:
        typer.echo("No collections found.")
        return

    for result in results:
        console.print(_format_result(result, cwd))

    failed = [r for r in results if not r.success]
    typer.echo(f"\n{len(results)} collection(s) checked, {len(failed)} with issues.")
    if failed:
        err_console.print(
            "\n".join(
                [
                    "\nTo investigate failures:",
                    *(
                        indent(
                            "photree collection check --collection-dir "
                            f'"{display_path(r.collection_dir, cwd)}"'
                        )
                        for r in failed
                    ),
                ]
            ),
            markup=False,
        )
        raise typer.Exit(code=1)
