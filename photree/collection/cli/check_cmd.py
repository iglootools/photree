"""The ``photree collection check`` command."""

from pathlib import Path

import typer

from photree.clihelpers.console import console, err_console
from photree.clihelpers.options import GALLERY_DIR_OPTION
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.collection.check import build_gallery_lookup, check_collection
from photree.collection.cli.app import app
from photree.collection.cli.options import COLLECTION_DIR_OPTION
from photree.collection.output import (
    format_collection_issue,
    format_issue_suggestions,
    format_unreadable_album,
)
from photree.common.formatting import CHECK, CROSS, indent, markup_escape
from photree.common.fs import display_path


@app.command("check")
def check_cmd(
    ctx: typer.Context,
    collection_dir: COLLECTION_DIR_OPTION = Path(),
    gallery_dir: GALLERY_DIR_OPTION = None,
) -> None:
    """Check collection integrity (member existence, date coverage)."""
    cwd = runtime_of(ctx).cwd()
    resolved_gallery = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    lookup = build_gallery_lookup(resolved_gallery)
    result = check_collection(collection_dir, lookup)
    for album_dir in lookup.unreadable_albums:
        err_console.print(format_unreadable_album(album_dir, cwd), markup=False)

    for issue in result.issues:
        console.print(
            indent(f"{CROSS} {markup_escape(format_collection_issue(issue))}"),
        )

    if result.success:
        console.print(f"{CHECK} {markup_escape(display_path(collection_dir, cwd))}")
    else:
        err_console.print(
            "\n".join(
                [
                    (
                        f"\n{len(result.issues)} issue(s) found in "
                        f"{display_path(collection_dir, cwd)}"
                    ),
                    *format_issue_suggestions(result.issues, collection_dir, cwd),
                ],
            ),
            markup=False,
        )
        raise typer.Exit(code=1)
