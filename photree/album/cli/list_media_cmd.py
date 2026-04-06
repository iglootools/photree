"""``photree album list-media`` command."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from ...common.fs import display_path
from ..id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
)
from ..store.media_metadata import load_media_metadata
from ..store.metadata import load_album_metadata
from . import album_app


@album_app.command("list-media")
def list_media_cmd(
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
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: text (default) or csv.",
        ),
    ] = "text",
    output_file: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Write output to a file instead of stdout.",
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
) -> None:
    """List all media items in an album."""
    cwd = Path.cwd()
    album_meta = load_album_metadata(album_dir)
    album_ext_id = (
        format_album_external_id(album_meta.id) if album_meta is not None else ""
    )
    media_meta = load_media_metadata(album_dir)

    if media_meta is None or not media_meta.media_sources:
        typer.echo("No media metadata found. Run 'photree album refresh' first.")
        raise typer.Exit(code=0)

    if output_format == "csv":
        _list_csv(album_dir, album_ext_id, media_meta, cwd, output_file)
    else:
        _list_text(album_dir, album_ext_id, media_meta, cwd)


def _list_csv(
    album_dir: Path,
    album_ext_id: str,
    media_meta: object,
    cwd: Path,
    output_file: Path | None,
) -> None:
    from ..store.media_metadata import MediaMetadata

    assert isinstance(media_meta, MediaMetadata)
    out = (
        open(output_file, "w", encoding="utf-8", newline="")
        if output_file
        else sys.stdout
    )
    try:
        writer = csv.writer(out)
        writer.writerow(["album_id", "media_source", "type", "id", "key"])
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
    finally:
        if output_file:
            out.close()


def _list_text(
    album_dir: Path,
    album_ext_id: str,
    media_meta: object,
    cwd: Path,
) -> None:
    from ..store.media_metadata import MediaMetadata

    assert isinstance(media_meta, MediaMetadata)
    typer.echo(f"Album: {display_path(album_dir, cwd)}")
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
