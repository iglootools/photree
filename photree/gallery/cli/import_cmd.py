"""The ``photree gallery import`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.cli.runtime import album_runtime_of
from photree.clihelpers.options import REIMPORT_OPTION
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.sysdeps import import_deps, require_system_deps
from photree.foundation.gallery_metadata import resolve_link_mode
from photree.foundation.linking import LinkMode
from photree.gallery.cli.app import app
from photree.gallery.cli.face_ops import cluster_faces_if_enabled
from photree.gallery.cli.import_ops import (
    plan_imports_or_exit,
    print_single_import_result,
    render_skipped,
    run_single_import,
)
from photree.gallery.cli.index_ops import build_index_or_exit
from photree.gallery.import_plan import ImportAction


@app.command("import")
def import_cmd(
    ctx: typer.Context,
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
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-g",
            help=(
                "Gallery root directory (or resolved from cwd "
                "via .photree/gallery.yaml)."
            ),
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
    *,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Print what would happen without modifying files.",
        ),
    ] = False,
    reimport: REIMPORT_OPTION = False,
) -> None:
    """Import an existing album directory into the gallery."""
    runtime = album_runtime_of(ctx)
    cwd = runtime.cwd()
    which = runtime.which
    require_system_deps(import_deps(), which=which)
    resolved_gallery = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    index = build_index_or_exit(resolved_gallery, cwd)

    import_plan = plan_imports_or_exit(
        [album_dir],
        index,
        resolved_gallery,
        cwd,
        reimport=reimport,
    )
    plan = import_plan.plans[0]

    if plan.action is ImportAction.SKIP:
        render_skipped([plan], cwd)
        raise typer.Exit(code=0)

    result = run_single_import(
        plan,
        resolved_gallery,
        resolved_lm,
        dry_run=dry_run,
        max_workers=runtime.cpu_count(),
        which=which,
        refresh=runtime.refresh,
        cwd=cwd,
    )
    print_single_import_result(
        result,
        cwd,
        link_mode=resolved_lm,
        dry_run=dry_run,
        which=which,
    )

    if not dry_run:
        cluster_faces_if_enabled(resolved_gallery)
