"""``photree gallery import-all`` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from ...clihelpers.console import err_console
from ...clihelpers.options import REIMPORT_OPTION
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...clihelpers.sysdeps import import_deps, require_system_deps
from ...common.formatting import indent
from ...common.fs import display_path
from ...fsprotocol import (
    GALLERY_YAML,
    PHOTREE_DIR,
    LinkMode,
    load_gallery_metadata,
    resolve_link_mode,
)
from ..cmd_handler.importer import BatchImportResult
from ..import_plan import AlbumPlan
from . import gallery_app
from .ops import (
    build_index_or_exit,
    plan_imports_or_exit,
    render_skipped,
    resolve_import_all_albums,
    run_batch_import,
    run_batch_post_import_check,
    run_face_clustering,
)


@gallery_app.command("import-all")
def import_all_cmd(
    base_dir: Annotated[
        Path | None,
        typer.Option(
            "--dir",
            "-d",
            help="Base directory to scan for album subdirectories.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    album_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to import (repeatable).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
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
    reimport: REIMPORT_OPTION = False,
) -> None:
    """Batch import album directories into the gallery.

    Either scan --dir for immediate subdirectories, or provide explicit
    album directories via --album-dir (repeatable). Copies each album to
    <gallery>/albums/YYYY/<album-name>/, generates missing IDs, refreshes
    JPEGs, and runs gallery-wide checks. Already-imported albums are skipped
    unless --reimport is given.
    """
    if base_dir is not None and album_dirs is not None:
        err_console.print("--dir and --album-dir are mutually exclusive.")
        raise typer.Exit(code=1)

    require_system_deps(import_deps())

    resolved_gallery = resolve_gallery_or_exit(gallery_dir)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)
    cwd = Path.cwd()

    albums = _resolve_albums_or_exit(base_dir, album_dirs, cwd)
    index = build_index_or_exit(resolved_gallery, cwd)
    import_plan = plan_imports_or_exit(
        albums, index, resolved_gallery, cwd, reimport=reimport
    )
    render_skipped(import_plan.skipped, cwd)

    to_import = import_plan.to_import
    if not to_import:
        typer.echo("Nothing to import.")
        raise typer.Exit(code=0)

    typer.echo(f"Found {len(to_import)} album(s).\n")
    typer.echo("Import:")
    result = run_batch_import(
        to_import, resolved_gallery, resolved_lm, dry_run, max_workers=os.cpu_count()
    )
    mutated = not dry_run and bool(result.imported)
    check_failed = _post_import_check(to_import, result, cwd) if mutated else []
    if mutated:
        _cluster_faces(resolved_gallery)

    _print_summary(result, check_failed, len(import_plan.skipped))
    if result.failures or check_failed:
        raise typer.Exit(code=1)


def _resolve_albums_or_exit(
    base_dir: Path | None, album_dirs: list[Path] | None, cwd: Path
) -> list[Path]:
    """Resolve the source albums, reporting skipped non-album directories."""
    albums, non_albums = resolve_import_all_albums(base_dir, album_dirs)
    if non_albums:
        typer.echo(
            "\n".join(
                [
                    f"Skipped {len(non_albums)} non-album director(ies):",
                    *(indent(str(display_path(s, cwd))) for s in non_albums),
                    "",
                ]
            )
        )
    if not albums:
        typer.echo("No album directories found.")
        raise typer.Exit(code=0)
    return albums


def _post_import_check(
    to_import: list[AlbumPlan], result: BatchImportResult, cwd: Path
) -> list[Path]:
    """Check every album that imported; return those that failed."""
    typer.echo("\nPost-Import Check:")
    imported = set(result.imported)
    check_failed = run_batch_post_import_check(
        [plan.target for plan in to_import if plan.source in imported], cwd
    )
    if check_failed:
        err_console.print(
            "\n".join(
                [
                    "\nTo investigate failures, run:",
                    *(
                        indent(
                            escape(
                                "'photree album check --album-dir "
                                f'"{display_path(target_dir, cwd)}"\''
                            )
                        )
                        for target_dir in check_failed
                    ),
                ]
            )
        )
    return check_failed


def _cluster_faces(gallery_dir: Path) -> None:
    """Refresh face clusters when the gallery has face detection enabled."""
    gallery_meta = load_gallery_metadata(gallery_dir / PHOTREE_DIR / GALLERY_YAML)
    if gallery_meta.faces_enabled:
        run_face_clustering(
            gallery_dir,
            distance_threshold=gallery_meta.face_cluster_threshold,
        )


def _print_summary(
    result: BatchImportResult, check_failed: list[Path], skipped: int
) -> None:
    """Print the tally: imports, import failures, check failures, and skips."""
    parts = [
        f"{len(result.imported)} album(s) imported",
        f"{len(result.failures)} failed",
        *([f"{len(check_failed)} failed post-import check"] if check_failed else []),
        *([f"{skipped} skipped"] if skipped else []),
    ]
    typer.echo(f"\nDone. {', '.join(parts)}.")
