"""``photree album list-media`` command."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import err_console
from ...clihelpers.csvout import csv_output
from ...clihelpers.options import OUTPUT_FILE_OPTION, OUTPUT_FORMAT_OPTION, OutputFormat
from ...common.formatting import indent
from ...common.fs import display_path
from ..id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
)
from ..store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    load_media_metadata,
)
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
    output_format: OUTPUT_FORMAT_OPTION = OutputFormat.TEXT,
    output_file: OUTPUT_FILE_OPTION = None,
) -> None:
    """List all media items in an album."""
    cwd = Path.cwd()
    album_meta = load_album_metadata(album_dir)
    album_ext_id = (
        format_album_external_id(album_meta.id) if album_meta is not None else ""
    )
    media_meta = load_media_metadata(album_dir)

    if media_meta is None or not media_meta.media_sources:
        message = (
            "No media metadata found. Run 'photree album refresh "
            f'--album-dir "{display_path(album_dir, cwd)}"\' first.'
        )
        # Keep stdout pure CSV: anything else goes to stderr in CSV mode.
        match output_format:
            case OutputFormat.CSV:
                err_console.print(message)
            case OutputFormat.TEXT:
                typer.echo(message)
        raise typer.Exit(code=0)

    match output_format:
        case OutputFormat.CSV:
            _list_csv(album_ext_id, media_meta, output_file)
        case OutputFormat.TEXT:
            typer.echo(_format_text(album_dir, album_ext_id, media_meta, cwd))


def _csv_rows(album_ext_id: str, media_meta: MediaMetadata) -> list[list[str]]:
    return [
        [album_ext_id, source_name, kind, format_id(mid), key]
        for source_name, source in media_meta.media_sources.items()
        for kind, ids, format_id in (
            ("image", source.images, format_image_external_id),
            ("video", source.videos, format_video_external_id),
        )
        for mid, key in ids.items()
    ]


def _list_csv(
    album_ext_id: str,
    media_meta: MediaMetadata,
    output_file: Path | None,
) -> None:
    with csv_output(output_file) as out:
        writer = csv.writer(out)
        writer.writerow(["album_id", "media_source", "type", "id", "key"])
        writer.writerows(_csv_rows(album_ext_id, media_meta))


def _source_lines(source: MediaSourceMediaMetadata) -> list[str]:
    """Unindented lines for one media source; the caller nests them."""
    return [
        *(
            [
                "images:",
                *(
                    indent(f"{format_image_external_id(mid)}: {key}")
                    for mid, key in source.images.items()
                ),
            ]
            if source.images
            else []
        ),
        *(
            [
                "videos:",
                *(
                    indent(f"{format_video_external_id(mid)}: {key}")
                    for mid, key in source.videos.items()
                ),
            ]
            if source.videos
            else []
        ),
    ]


def _format_text(
    album_dir: Path,
    album_ext_id: str,
    media_meta: MediaMetadata,
    cwd: Path,
) -> str:
    body = [
        *([f"id: {album_ext_id}"] if album_ext_id else []),
        *(
            line
            for source_name, source in media_meta.media_sources.items()
            for line in [
                f"{source_name}:",
                *(indent(sl) for sl in _source_lines(source)),
            ]
        ),
    ]
    return "\n".join(
        [f"Album: {display_path(album_dir, cwd)}", *(indent(line) for line in body)]
    )
