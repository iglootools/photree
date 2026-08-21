"""``albums stats`` / ``gallery stats`` wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ....album.stats import models as stats_models
from ....album.stats import output as stats_output
from ....clihelpers.console import console, err_console
from ....clihelpers.progress import BatchProgressBar
from ....common.fs import display_path
from ...cmd_handler.stats import batch_stats
from ..ops import make_display_fn


def run_batch_stats(
    albums: list[Path],
    display_base: Path | None,
    *,
    gallery_dir: Path | None = None,
) -> None:
    """Shared implementation for gallery stats / albums stats."""
    from ....album.naming import parse_album_name

    cwd = Path.cwd()

    if not albums:
        typer.echo("No albums found.")
        raise typer.Exit(code=0)

    unparseable = [a for a in albums if parse_album_name(a.name) is None]
    if unparseable:
        err_console.print(
            f"{len(unparseable)} album(s) have unparseable names. "
            f"Run photree albums check to identify and fix naming issues:"
        )
        for album_dir in unparseable:
            err_console.print(f"  {display_path(album_dir, cwd)}")
        raise typer.Exit(code=1)

    if display_base is not None:
        typer.echo(f"Found {len(albums)} album(s).\n")

    with BatchProgressBar(
        total=len(albums), description="Computing stats", done_description="stats"
    ) as progress:
        result = batch_stats(
            albums,
            display_fn=make_display_fn(display_base, cwd),
            on_start=progress.on_start,
            on_end=lambda name, success: progress.on_end(name, success=success),
        )

    if gallery_dir is not None:
        result = _enrich_gallery_stats(result, gallery_dir)

    typer.echo("")
    console.print(stats_output.format_gallery_stats(result))


def _enrich_gallery_stats(
    result: stats_models.GalleryStats, gallery_dir: Path
) -> stats_models.GalleryStats:
    """Add collection stats and gallery-level cache storage from gallery context."""
    from ....album.stats.aggregate import merge_size_stats
    from ....album.stats.scan import scan_directory_size
    from ....collection.stats import compute_gallery_collection_stats
    from ....gallery.faces.manifest import gallery_faces_dir

    col_stats = compute_gallery_collection_stats(gallery_dir)

    # Gallery-level face index storage (clusters, FAISS index, manifest)
    gallery_face_size = scan_directory_size(gallery_faces_dir(gallery_dir))
    cache_storage = merge_size_stats(
        [s for s in [result.cache_storage, gallery_face_size] if s.file_count > 0]
    )

    return stats_models.GalleryStats(
        album_count=result.album_count,
        by_album=result.by_album,
        aggregate=result.aggregate,
        unique_media_source_names=result.unique_media_source_names,
        by_year=result.by_year,
        collection_stats=col_stats,
        cache_storage=cache_storage if cache_storage.file_count > 0 else None,
    )
