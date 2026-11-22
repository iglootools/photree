from pathlib import Path

import typer

from photree.albums.batchcli.failures import exit_if_no_albums, exit_with_failures
from photree.albums.batchcli.resolution import make_display_fn
from photree.albums.cmd_handler.detect_faces import batch_detect_faces
from photree.clihelpers.progress import BatchProgressBar
from photree.common.formatting import format_dry_run


def run_batch_detect_faces(
    albums: list[Path],
    display_base: Path | None,
    *,
    redetect: bool = False,
    refresh_thumbs: bool = False,
    dry_run: bool = False,
    cwd: Path,
    max_workers: int | None,
) -> None:
    """Run face detection on *albums*, print a summary, exit 1 on any failure."""
    exit_if_no_albums(albums, display_base)

    with BatchProgressBar(
        total=len(albums),
        description="Detecting faces",
        done_description="detect-faces",
    ) as progress:
        result = batch_detect_faces(
            albums,
            redetect=redetect,
            refresh_thumbs=refresh_thumbs,
            dry_run=dry_run,
            display_fn=make_display_fn(display_base, cwd),
            max_workers=max_workers,
            on_start=progress.on_start,
            on_end=lambda name, success, errors: progress.on_end(
                name, success=success, error_labels=errors
            ),
        )

    tally = (
        f"{result.succeeded} album(s) would be processed"
        if dry_run
        else f"Done. {result.succeeded} album(s) processed"
    )
    typer.echo(
        format_dry_run(f"\n{tally}, {len(result.failures)} failed.", dry_run=dry_run)
    )
    exit_with_failures(result.failures, "detect-faces", cwd)
