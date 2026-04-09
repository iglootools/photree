"""``photree album refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console
from ...clihelpers.progress import StageProgressBar
from ...common.formatting import CHECK
from ..exif_cache.refresh import refresh_exif_cache
from ..faces.refresh import refresh_face_data
from ..refresh import RefreshResult, refresh_media_metadata
from . import album_app

# Stage names for the album refresh pipeline
_STAGE_MEDIA_IDS = "media-ids"
_STAGE_EXIF_CACHE = "exif-cache"
_STAGE_FACES = "faces"


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
    with StageProgressBar(
        total=3,
        labels={
            _STAGE_MEDIA_IDS: "Refreshing media IDs",
            _STAGE_EXIF_CACHE: "Refreshing EXIF cache",
            _STAGE_FACES: "Refreshing face detection",
        },
    ) as progress:
        progress.on_start(_STAGE_MEDIA_IDS)
        media_result = refresh_media_metadata(album_dir, dry_run=dry_run)
        progress.on_end(_STAGE_MEDIA_IDS)

        if not media_result.by_media_source:
            typer.echo("No media sources with archives found.")
            raise typer.Exit(code=0)

        progress.on_start(_STAGE_EXIF_CACHE)
        exif_result = refresh_exif_cache(album_dir, dry_run=dry_run)
        progress.on_end(_STAGE_EXIF_CACHE)

        progress.on_start(_STAGE_FACES)
        face_result = refresh_face_data(
            album_dir,
            redetect=redetect_faces,
            refresh_thumbs=refresh_face_thumbs,
            dry_run=dry_run,
        )
        progress.on_end(_STAGE_FACES)

    _print_summary(media_result, exif_result, face_result)


# ---------------------------------------------------------------------------
# Summary output
# ---------------------------------------------------------------------------


def _print_summary(
    media_result: RefreshResult,
    exif_result: object,
    face_result: object,
) -> None:
    """Print one-line summaries for each refresh step."""
    from ..exif_cache.refresh import ExifCacheRefreshResult
    from ..faces.refresh import FaceRefreshResult

    # Media IDs
    if media_result.changed:
        parts = [
            f"{media_result.total_new} new",
            *(
                [f"{media_result.total_removed} removed"]
                if media_result.total_removed
                else []
            ),
        ]
        console.print(f"  {CHECK} media-ids ({', '.join(parts)})")
    else:
        console.print(f"  {CHECK} media-ids (no changes)")

    # EXIF cache
    if isinstance(exif_result, ExifCacheRefreshResult) and exif_result.changed:
        total_refreshed = exif_result.total_refreshed
        console.print(f"  {CHECK} exif-cache ({total_refreshed} refreshed)")
    else:
        console.print(f"  {CHECK} exif-cache (no changes)")

    # Faces
    if isinstance(face_result, FaceRefreshResult) and face_result.changed:
        parts = [f"{face_result.total_processed} processed"]
        if face_result.total_faces:
            parts.append(f"{face_result.total_faces} face(s)")
        console.print(f"  {CHECK} faces ({', '.join(parts)})")
    else:
        console.print(f"  {CHECK} faces (no changes)")
