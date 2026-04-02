"""``photree gallery import`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...fs import LinkMode, resolve_link_mode
from .ops import (
    build_index_or_exit,
    print_single_import_result,
    resolve_gallery_or_exit,
    run_single_import,
    validate_single_import_or_exit,
)


@gallery_app.command("import")
def import_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to import into the gallery.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
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
    link_mode: Annotated[
        LinkMode | None,
        typer.Option(
            "--link-mode",
            help="How to create main files: hardlink (default), symlink, or copy.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
) -> None:
    """Import an existing album directory into the gallery.

    Copies the album to <gallery>/albums/YYYY/<album-name>/, generates a
    missing album ID, refreshes JPEGs if stale, optimizes links, and runs
    integrity checks.
    """
    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()
    index = build_index_or_exit(resolved_gallery, cwd)

    validate_single_import_or_exit(album_dir, index, resolved_gallery, cwd)
    result = run_single_import(album_dir, resolved_gallery, resolved_lm, dry_run)
    print_single_import_result(result, cwd, dry_run)
