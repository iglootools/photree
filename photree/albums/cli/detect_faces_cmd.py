"""``photree albums detect-faces`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...album.faces.detect import memoized_face_analyzer_factory
from ...album.faces.refresh import refresh_face_data
from ...clihelpers.console import err_console
from ...clihelpers.progress import BatchProgressBar
from ...clihelpers.sysdeps import FACE_DETECTION_DEPS, require_system_deps
from ...common.fs import display_path
from . import AlbumDirOption, DirOption, albums_app
from .ops import make_display_fn, resolve_check_batch_albums


@albums_app.command("detect-faces")
def detect_faces_cmd(
    base_dir: DirOption = None,
    album_dirs: AlbumDirOption = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would change without writing."),
    ] = False,
    redetect: Annotated[
        bool,
        typer.Option(
            "--redetect",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    refresh_thumbs: Annotated[
        bool,
        typer.Option(
            "--refresh-thumbs",
            help="Refresh face detection thumbnails from originals.",
        ),
    ] = False,
) -> None:
    """Run face detection on images in multiple albums."""
    require_system_deps(FACE_DETECTION_DEPS)

    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    cwd = Path.cwd()

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")

    analyzer_factory = memoized_face_analyzer_factory()
    failures: list[tuple[Path, str]] = []
    display_fn = make_display_fn(display_base, cwd)

    with BatchProgressBar(
        total=len(albums),
        description="Detecting faces",
        done_description="detect-faces",
    ) as progress:
        for album_dir in albums:
            album_name = display_fn(album_dir)
            progress.on_start(album_name)
            try:
                result = refresh_face_data(
                    album_dir,
                    analyzer_factory=analyzer_factory,
                    redetect=redetect,
                    refresh_thumbs=refresh_thumbs,
                    dry_run=dry_run,
                )
            except Exception as exc:
                progress.on_end(album_name, success=False, error_labels=(str(exc),))
                failures.append((album_dir, str(exc)))
            else:
                labels = tuple(
                    f"{ms}/{f.key} ({f.stage}): {f.reason}" for ms, f in result.failures
                )
                progress.on_end(album_name, success=not labels, error_labels=labels)
                if labels:
                    failures.append((album_dir, "; ".join(labels)))

    if failures:
        err_console.print("\nFailed albums:")
        for album_dir, reason in failures:
            err_console.print(f"  {display_path(album_dir, cwd)}\n    {reason}")
        err_console.print("\nTo investigate failures:")
        for album_dir, _ in failures:
            err_console.print(
                f'  photree album detect-faces --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)
