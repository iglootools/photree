"""The ``photree album detect-faces`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album.cli.app import app
from photree.album.cli.media_source_conflict import exit_on_media_source_conflict
from photree.album.faces.detect import memoized_face_analyzer_factory
from photree.album.faces.failures import format_face_failures
from photree.album.faces.refresh import FaceSourceRefreshResult, refresh_face_data
from photree.clihelpers.console import err_console
from photree.clihelpers.options import DRY_RUN_OPTION
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.sysdeps import FACE_DETECTION_DEPS, require_system_deps
from photree.common.formatting import format_dry_run, indent


@app.command("detect-faces")
def detect_faces_cmd(
    ctx: typer.Context,
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path(),
    *,
    dry_run: DRY_RUN_OPTION = False,
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
    """Run face detection on album images."""
    runtime = runtime_of(ctx)
    require_system_deps(FACE_DETECTION_DEPS, which=runtime.which)

    with exit_on_media_source_conflict(runtime.cwd()):
        result = refresh_face_data(
            album_dir,
            analyzer_factory=memoized_face_analyzer_factory(),
            redetect=redetect,
            refresh_thumbs=refresh_thumbs,
            dry_run=dry_run,
            max_workers=runtime.cpu_count(),
        )

    if not result.by_media_source:
        typer.echo("No media sources with archives found.")
        raise typer.Exit(code=0)

    for ms_name, ms_result in result.by_media_source:
        typer.echo(
            indent(
                format_dry_run(
                    f"{ms_name}: {_source_summary(ms_result, dry_run=dry_run)}",
                    dry_run=dry_run,
                ),
            ),
        )

    if result.failures:
        err_console.print("\nFailed images:")
        for line in format_face_failures(result.failures):
            err_console.print(indent(line), markup=False)
        raise typer.Exit(code=1)


def _source_summary(ms_result: FaceSourceRefreshResult, *, dry_run: bool) -> str:
    return ", ".join(
        [
            f"{ms_result.processed} {'would be processed' if dry_run else 'processed'}",
            f"{ms_result.skipped} skipped",
            *(
                [f"{ms_result.faces_detected} face(s)"]
                if ms_result.faces_detected
                else []
            ),
            *([f"{ms_result.failed} failed"] if ms_result.failed else []),
        ],
    )
