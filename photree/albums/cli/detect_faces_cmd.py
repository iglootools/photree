"""``photree albums detect-faces`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...album.faces.detect import create_face_analyzer
from ...album.faces.refresh import refresh_face_data
from ...clihelpers.console import err_console
from ...clihelpers.progress import BatchProgressBar, run_with_spinner
from ...common.fs import display_path
from . import AlbumDirOption, DirOption, albums_app
from .batch_ops import make_display_fn
from .ops import resolve_check_batch_albums


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
    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs)
    cwd = Path.cwd()

    if not albums:
        typer.echo("\nNo albums found.")
        raise typer.Exit(code=0)

    if display_base is not None:
        typer.echo(f"\nFound {len(albums)} album(s).\n")

    face_analyzer = run_with_spinner(
        "Loading face detection model...", create_face_analyzer
    )
    failed_albums: list[Path] = []
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
                refresh_face_data(
                    album_dir,
                    face_analyzer=face_analyzer,
                    redetect=redetect,
                    refresh_thumbs=refresh_thumbs,
                    dry_run=dry_run,
                )
                progress.on_end(album_name, success=True)
            except Exception:
                progress.on_end(album_name, success=False)
                failed_albums.append(album_dir)

    if failed_albums:
        err_console.print("\nFailed albums:")
        for album_dir in failed_albums:
            err_console.print(
                f'  photree album detect-faces --album-dir "{display_path(album_dir, cwd)}"'
            )
        raise typer.Exit(code=1)
