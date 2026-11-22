"""``albums refresh`` / ``gallery refresh`` wrapper."""

from pathlib import Path

import typer

from photree.albums.batchcli.failures import exit_if_no_albums, exit_with_failures
from photree.albums.batchcli.resolution import make_display_fn
from photree.albums.cmd_handler.refresh import batch_refresh
from photree.clihelpers.progress import BatchProgressBar
from photree.clihelpers.runtime import Runtime
from photree.common.formatting import format_dry_run
from photree.foundation.gallery_metadata import resolve_link_mode


def run_batch_refresh(
    albums: list[Path],
    display_base: Path | None,
    *,
    dry_run: bool = False,
    force_browsable: bool = False,
    force_jpeg: bool = False,
    force_exif_cache: bool = False,
    redetect_faces: bool = False,
    refresh_face_thumbs: bool = False,
    runtime: Runtime,
) -> None:
    """Shared implementation for albums refresh / gallery refresh."""
    cwd = runtime.cwd()
    exit_if_no_albums(albums, display_base)

    with BatchProgressBar(
        total=len(albums),
        description="Refreshing",
        done_description="refresh",
    ) as progress:
        result = batch_refresh(
            albums,
            link_mode_for=lambda album_dir: resolve_link_mode(None, album_dir),
            dry_run=dry_run,
            force_browsable=force_browsable,
            force_jpeg=force_jpeg,
            force_exif_cache=force_exif_cache,
            redetect_faces=redetect_faces,
            refresh_face_thumbs=refresh_face_thumbs,
            display_fn=make_display_fn(display_base, cwd),
            which=runtime.which,
            max_workers=runtime.cpu_count(),
            on_start=progress.on_start,
            on_end=progress.on_end,
        )

    typer.echo(
        format_dry_run(
            (
                f"\n{result.refreshed} album(s) would be refreshed"
                if dry_run
                else f"\nDone. {result.refreshed} album(s) refreshed"
            )
            + f", {len(result.failures)} failed.",
            dry_run=dry_run,
        ),
    )
    exit_with_failures(result.failures, "refresh", cwd)
