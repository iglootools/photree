"""``photree album refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..exif_cache.refresh import refresh_exif_cache
from ..faces.refresh import refresh_face_data
from ..refresh import refresh_media_metadata
from . import album_app


@album_app.command("refresh")
def refresh_cmd(
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
    ] = Path("."),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would change without writing."),
    ] = False,
    redetect_faces: Annotated[
        bool,
        typer.Option(
            "--redetect-faces",
            help="Re-run face detection on all images (reuses cached thumbnails).",
        ),
    ] = False,
    refresh_face_thumbs: Annotated[
        bool,
        typer.Option(
            "--refresh-face-thumbs",
            help="Refresh face detection thumbnails from originals.",
        ),
    ] = False,
) -> None:
    """Refresh media IDs, EXIF cache, and face detection data."""
    result = refresh_media_metadata(album_dir, dry_run=dry_run)

    if not result.by_media_source:
        typer.echo("No media sources with archives found.")
        raise typer.Exit(code=0)

    _print_media_ids_result(result)
    _print_exif_cache_result(album_dir, dry_run=dry_run)
    _print_face_detection_result(
        album_dir,
        redetect_faces=redetect_faces,
        refresh_face_thumbs=refresh_face_thumbs,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_media_ids_result(result: object) -> None:
    """Print media ID refresh results."""
    from ..refresh import RefreshResult

    if not isinstance(result, RefreshResult):
        return

    typer.echo("Media IDs:")
    if not result.changed:
        typer.echo("  no changes")
    else:
        for ms_name, ms_result in result.by_media_source:
            parts = [
                f"{ms_result.new_images} new image(s)",
                f"{ms_result.new_videos} new video(s)",
            ]
            if ms_result.removed_images or ms_result.removed_videos:
                parts.append(
                    f"{ms_result.removed_images + ms_result.removed_videos} removed"
                )
            typer.echo(f"  {ms_name}: {', '.join(parts)}")


def _print_exif_cache_result(album_dir: Path, *, dry_run: bool) -> None:
    """Refresh and print EXIF cache results."""
    typer.echo("\nEXIF cache:")
    exif_result = refresh_exif_cache(album_dir, dry_run=dry_run)
    if not exif_result.by_media_source:
        typer.echo("  no media sources")
    elif not exif_result.changed:
        typer.echo("  no changes")
    else:
        for ms_name, ms_result in exif_result.by_media_source:
            if ms_result.changed:
                parts = [f"{ms_result.refreshed} refreshed"]
                if ms_result.pruned:
                    parts.append(f"{ms_result.pruned} pruned")
                typer.echo(f"  {ms_name}: {', '.join(parts)}")


def _print_face_detection_result(
    album_dir: Path,
    *,
    redetect_faces: bool,
    refresh_face_thumbs: bool,
    dry_run: bool,
) -> None:
    """Refresh and print face detection results."""
    typer.echo("\nFaces:")
    face_result = refresh_face_data(
        album_dir,
        redetect=redetect_faces,
        refresh_thumbs=refresh_face_thumbs,
        dry_run=dry_run,
    )

    if not face_result.by_media_source:
        typer.echo("  no media sources")
    elif not face_result.changed:
        typer.echo("  no changes")
    else:
        for ms_name, ms_result in face_result.by_media_source:
            if ms_result.changed:
                parts = [f"{ms_result.processed} processed"]
                if ms_result.faces_detected:
                    parts.append(f"{ms_result.faces_detected} face(s)")
                if ms_result.failed:
                    parts.append(f"{ms_result.failed} failed")
                typer.echo(f"  {ms_name}: {', '.join(parts)}")
