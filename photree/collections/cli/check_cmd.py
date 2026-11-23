"""The ``photree collections check`` command."""

from pathlib import Path

import typer

from photree.clihelpers.console import console, err_console
from photree.clihelpers.options import GALLERY_DIR_OPTION
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.collection.check import (
    CollectionCheckResult,
    build_gallery_lookup,
    check_all_collections,
)
from photree.collection.output import (
    format_collection_issue,
    format_unreadable_album,
)
from photree.collections.cli.app import app
from photree.common.formatting import CHECK, CROSS, indent, markup_escape
from photree.common.fs import display_path


def _format_result(result: CollectionCheckResult, cwd: Path) -> str:
    """One check line, followed by the indented issues on failure (Rich markup)."""
    name = markup_escape(display_path(result.collection_dir, cwd))
    return (
        f"{CHECK} {name}"
        if result.success
        else "\n".join(
            [
                f"{CROSS} {name}",
                *(
                    indent(markup_escape(format_collection_issue(i)), 2)
                    for i in result.issues
                ),
            ],
        )
    )


@app.command("check")
def check_cmd(
    ctx: typer.Context,
    gallery_dir: GALLERY_DIR_OPTION = None,
) -> None:
    """Check all collections in the gallery."""
    cwd = runtime_of(ctx).cwd()
    resolved_gallery = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    lookup = build_gallery_lookup(resolved_gallery)
    results = check_all_collections(resolved_gallery, lookup)
    for album_dir in lookup.unreadable_albums:
        err_console.print(format_unreadable_album(album_dir, cwd), markup=False)

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
                            f'"{display_path(r.collection_dir, cwd)}"',
                        )
                        for r in failed
                    ),
                ],
            ),
            markup=False,
        )
        raise typer.Exit(code=1)
