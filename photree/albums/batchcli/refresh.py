"""``albums refresh`` / ``gallery refresh`` wrapper."""

from pathlib import Path

import typer

from photree.albums.batchcli.failures import announce_albums, exit_with_failures
from photree.albums.batchcli.resolution import make_display_fn
from photree.albums.cmd_handler.refresh import batch_refresh
from photree.albums.output.refresh import describe_refresh_error
from photree.clihelpers.progress import BatchProgressBar
from photree.clihelpers.runtime import Runtime
from photree.common.formatting import format_dry_run, format_flags
from photree.foundation.gallery_metadata import resolve_link_mode


def refresh_retry_flags(
    *,
    force_browsable: bool,
    force_jpeg: bool,
    force_exif_cache: bool,
    redetect_faces: bool,
    refresh_face_thumbs: bool,
    dry_run: bool,
) -> list[tuple[str, bool]]:
    """Pair each flag a ``refresh`` retry repeats with whether the run used it."""
    return [
        ("--refresh-browsable", force_browsable),
        ("--refresh-jpeg", force_jpeg),
        ("--refresh-exif-cache", force_exif_cache),
        ("--redetect-faces", redetect_faces),
        ("--refresh-face-thumbs", refresh_face_thumbs),
        ("--dry-run", dry_run),
    ]


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
    """
    Shared implementation for albums refresh / gallery refresh.

    Returns when there are no albums, rather than exiting, so that gallery
    refresh still refreshes the collections and ``browsable/``. Exits 1 when
    any album failed.
    """
    cwd = runtime.cwd()
    if not announce_albums(albums, display_base):
        return

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
            describe_error=describe_refresh_error,
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
    exit_with_failures(
        result.failures,
        "refresh",
        cwd,
        extra_flags=format_flags(
            refresh_retry_flags(
                force_browsable=force_browsable,
                force_jpeg=force_jpeg,
                force_exif_cache=force_exif_cache,
                redetect_faces=redetect_faces,
                refresh_face_thumbs=refresh_face_thumbs,
                dry_run=dry_run,
            ),
        ),
    )
