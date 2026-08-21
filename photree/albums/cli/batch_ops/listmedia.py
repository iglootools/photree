"""``albums list-media`` / ``gallery list-media`` wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ....album.id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
)
from ....album.store.metadata import load_album_metadata
from ..ops import display_name


def run_batch_list_media(
    albums: list[Path],
    display_base: Path | None,
    *,
    output_format: str = "text",
    output_file: Path | None = None,
) -> None:
    """Shared implementation for albums list-media / gallery list-media."""
    import csv

    from ....album.store.media_metadata import load_media_metadata
    from ....clihelpers.csvout import csv_output

    cwd = Path.cwd()

    if not albums:
        typer.echo("No albums found.", err=output_format == "csv")
        raise typer.Exit(code=0)

    if output_format == "csv":
        with csv_output(output_file) as out:
            writer = csv.writer(out)
            writer.writerow(["album_id", "media_source", "type", "id", "key"])
            for album_dir in albums:
                album_meta = load_album_metadata(album_dir)
                album_ext_id = (
                    format_album_external_id(album_meta.id)
                    if album_meta is not None
                    else ""
                )
                media_meta = load_media_metadata(album_dir)
                if media_meta is None:
                    continue
                for source_name, source in media_meta.media_sources.items():
                    for mid, key in source.images.items():
                        writer.writerow(
                            [
                                album_ext_id,
                                source_name,
                                "image",
                                format_image_external_id(mid),
                                key,
                            ]
                        )
                    for mid, key in source.videos.items():
                        writer.writerow(
                            [
                                album_ext_id,
                                source_name,
                                "video",
                                format_video_external_id(mid),
                                key,
                            ]
                        )
        return

    for album_dir in albums:
        name = display_name(album_dir, display_base, cwd)
        album_meta = load_album_metadata(album_dir)
        album_ext_id = (
            format_album_external_id(album_meta.id) if album_meta is not None else ""
        )
        media_meta = load_media_metadata(album_dir)
        if media_meta is None or not media_meta.media_sources:
            continue

        typer.echo(f"{name}")
        if album_ext_id:
            typer.echo(f"  id: {album_ext_id}")
        for source_name, source in media_meta.media_sources.items():
            typer.echo(f"  {source_name}:")
            if source.images:
                typer.echo("    images:")
                for mid, key in source.images.items():
                    typer.echo(f"      {format_image_external_id(mid)}: {key}")
            if source.videos:
                typer.echo("    videos:")
                for mid, key in source.videos.items():
                    typer.echo(f"      {format_video_external_id(mid)}: {key}")
