"""The ``photree gallery import-all`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.clihelpers.console import err_console
from photree.clihelpers.options import REIMPORT_OPTION
from photree.clihelpers.resolution import resolve_gallery_or_exit
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.sysdeps import import_deps, require_system_deps
from photree.clihelpers.usage import mutually_exclusive_error
from photree.common.formatting import format_dry_run, indent, markup_escape
from photree.common.fs import display_path
from photree.common.sysdeps import WhichFn
from photree.foundation.gallery_metadata import resolve_link_mode
from photree.foundation.linking import LinkMode
from photree.gallery.cli.app import app
from photree.gallery.cli.face_ops import cluster_faces_if_enabled
from photree.gallery.cli.import_ops import (
    plan_imports_or_exit,
    render_skipped,
    resolve_import_all_albums,
    run_batch_import,
    run_batch_post_import_check,
)
from photree.gallery.cli.index_ops import build_index_or_exit
from photree.gallery.cmd_handler.importer import BatchImportResult
from photree.gallery.import_plan import AlbumPlan
from photree.gallery.output import format_import_all_summary, import_all_failed


@app.command("import-all")
def import_all_cmd(
    ctx: typer.Context,
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
    """
    Batch import album directories into the gallery.

    Either scan --dir for immediate subdirectories, or provide explicit
    album directories via --album-dir (repeatable). Copies each album to
    <gallery>/albums/YYYY/<album-name>/, generates missing IDs, refreshes
    JPEGs, and runs gallery-wide checks. Already-imported albums are skipped
    unless --reimport is given.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    which = runtime.which
    if base_dir is not None and album_dirs is not None:
        raise mutually_exclusive_error(("--dir", "--album-dir"))

    require_system_deps(import_deps(), which=which)

    resolved_gallery = resolve_gallery_or_exit(gallery_dir, cwd=cwd)
    resolved_lm = resolve_link_mode(link_mode, resolved_gallery)

    albums = _resolve_albums_or_exit(base_dir, album_dirs, cwd)
    index = build_index_or_exit(resolved_gallery, cwd)
    import_plan = plan_imports_or_exit(
        albums,
        index,
        resolved_gallery,
        cwd,
        reimport=reimport,
    )
    render_skipped(import_plan.skipped, cwd)

    to_import = import_plan.to_import
    if not to_import:
        typer.echo("Nothing to import.")
        raise typer.Exit(code=0)

    typer.echo(f"Found {len(to_import)} album(s).\n")
    typer.echo("Import:")
    result = run_batch_import(
        to_import,
        resolved_gallery,
        resolved_lm,
        dry_run=dry_run,
        max_workers=runtime.cpu_count(),
        which=which,
        cwd=cwd,
    )
    mutated = not dry_run and bool(result.imported)
    check_failed = (
        _post_import_check(to_import, result, resolved_gallery, cwd, which=which)
        if mutated
        else []
    )
    if mutated:
        cluster_faces_if_enabled(resolved_gallery)

    typer.echo(
        format_dry_run(
            "\n"
            + format_import_all_summary(
                result,
                check_failed,
                len(import_plan.skipped),
                dry_run=dry_run,
            ),
            dry_run=dry_run,
        ),
    )
    if import_all_failed(result, check_failed):
        raise typer.Exit(code=1)


def _resolve_albums_or_exit(
    base_dir: Path | None,
    album_dirs: list[Path] | None,
    cwd: Path,
) -> list[Path]:
    """Resolve the source albums, reporting skipped non-album directories."""
    albums, non_albums = resolve_import_all_albums(base_dir, album_dirs, cwd=cwd)
    if non_albums:
        typer.echo(
            "\n".join(
                [
                    f"Skipped {len(non_albums)} non-album director(ies):",
                    *(indent(str(display_path(s, cwd))) for s in non_albums),
                    "",
                ],
            ),
        )
    if not albums:
        typer.echo("No album directories found.")
        raise typer.Exit(code=0)
    return albums


def _post_import_check(
    to_import: list[AlbumPlan],
    result: BatchImportResult,
    gallery_dir: Path,
    cwd: Path,
    *,
    which: WhichFn,
) -> list[Path]:
    """Check every album that imported; return those that failed."""
    typer.echo("\nPost-Import Check:")
    imported = set(result.imported)
    check_failed = run_batch_post_import_check(
        [plan.target for plan in to_import if plan.source in imported],
        gallery_dir,
        cwd,
        which=which,
    )
    if check_failed:
        err_console.print(
            "\n".join(
                [
                    "\nTo investigate failures, run:",
                    *(
                        indent(
                            markup_escape(
                                "'photree album check --album-dir "
                                f'"{display_path(target_dir, cwd)}"\'',
                            ),
                        )
                        for target_dir in check_failed
                    ),
                ],
            ),
        )
    return check_failed
