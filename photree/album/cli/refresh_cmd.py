"""``photree album refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...common.fs import display_path
from ...fsprotocol import PHOTREE_DIR
from ..exif_cache.refresh import refresh_exif_cache
from ..faces.refresh import refresh_face_data
from ..refresh import refresh_media_metadata
from ..store.protocol import MEDIA_YAML
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
    """Refresh media metadata and face detection data."""
    cwd = Path.cwd()
    result = refresh_media_metadata(album_dir, dry_run=dry_run)

    if not result.by_media_source:
        typer.echo("No media sources with archives found.")
        raise typer.Exit(code=0)

    media_yaml = album_dir / PHOTREE_DIR / MEDIA_YAML
    if dry_run:
        typer.echo(f"[dry run] Would write {display_path(media_yaml, cwd)}")
    else:
        typer.echo(f"Refreshed {display_path(media_yaml, cwd)}")

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

    # EXIF cache
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

    # Face detection
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
