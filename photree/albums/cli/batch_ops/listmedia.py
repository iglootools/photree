"""``albums list-media`` / ``gallery list-media`` wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from ....album.id import (
    format_album_external_id,
    format_image_external_id,
    format_video_external_id,
)
from ....album.store.media_metadata import (
    MediaMetadata,
    MediaSourceMediaMetadata,
    load_media_metadata,
)
from ....album.store.metadata import load_album_metadata
from ....clihelpers.options import OutputFormat
from ....common.formatting import indent
from ..ops import display_name
from .sink import write_csv, write_text

_CSV_HEADER = ("album_id", "media_source", "type", "id", "key")


@dataclass(frozen=True)
class _AlbumMedia:
    name: str
    album_ext_id: str  # "" when the album has no ID
    media: MediaMetadata


def _load(albums: list[Path], display_base: Path | None) -> list[_AlbumMedia]:
    """Albums that have media IDs, in order."""
    cwd = Path.cwd()
    return [
        _AlbumMedia(
            display_name(album_dir, display_base, cwd),
            format_album_external_id(meta.id) if meta is not None else "",
            media,
        )
        for album_dir in albums
        for media in [load_media_metadata(album_dir)]
        if media is not None
        for meta in [load_album_metadata(album_dir)]
    ]


def _csv_rows(albums: list[_AlbumMedia]) -> list[list[str]]:
    return [
        [album.album_ext_id, source_name, kind, fmt(mid), key]
        for album in albums
        for source_name, source in album.media.media_sources.items()
        for kind, ids, fmt in (
            ("image", source.images, format_image_external_id),
            ("video", source.videos, format_video_external_id),
        )
        for mid, key in ids.items()
    ]


def _source_lines(source_name: str, source: MediaSourceMediaMetadata) -> list[str]:
    """Unindented lines for one media source (nested levels indented here)."""
    return [
        f"{source_name}:",
        *(
            line
            for label, ids, fmt in (
                ("images", source.images, format_image_external_id),
                ("videos", source.videos, format_video_external_id),
            )
            if ids
            for line in [
                indent(f"{label}:"),
                *(indent(f"{fmt(mid)}: {key}", 2) for mid, key in ids.items()),
            ]
        ),
    ]


def _text_lines(albums: list[_AlbumMedia]) -> list[str]:
    return [
        line
        for album in albums
        if album.media.media_sources
        for line in [
            album.name,
            *([indent(f"id: {album.album_ext_id}")] if album.album_ext_id else []),
            *(
                indent(source_line)
                for name, source in album.media.media_sources.items()
                for source_line in _source_lines(name, source)
            ),
        ]
    ]


def run_batch_list_media(
    albums: list[Path],
    display_base: Path | None,
    *,
    output_format: OutputFormat = OutputFormat.TEXT,
    output_file: Path | None = None,
) -> None:
    """Shared implementation for albums list-media / gallery list-media.

    *output_file* applies to both formats.
    """
    if not albums:
        typer.echo("No albums found.", err=output_format == OutputFormat.CSV)
        raise typer.Exit(code=0)

    loaded = _load(albums, display_base)
    match output_format:
        case OutputFormat.CSV:
            write_csv(_CSV_HEADER, _csv_rows(loaded), output_file)
        case OutputFormat.TEXT:
            write_text(_text_lines(loaded), output_file)
