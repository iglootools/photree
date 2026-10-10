"""``photree album show`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...common.formatting import indent
from ...common.fs import display_path
from ..id import format_album_external_id
from ..naming import ParsedAlbumName, parse_album_name
from ..store.media_sources_discovery import discover_media_sources
from ..store.metadata import load_album_metadata
from . import album_app
from .media_source_conflict import exit_on_media_source_conflict


@album_app.command("show")
def show_cmd(
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
) -> None:
    """Display album metadata and parsed name."""
    cwd = Path.cwd()
    metadata = load_album_metadata(album_dir)
    with exit_on_media_source_conflict(cwd):
        media_sources = discover_media_sources(album_dir)

    typer.echo(f"Album: {display_path(album_dir, cwd)}")
    details = [
        f"directory: {album_dir.name}",
        f"id: {format_album_external_id(metadata.id)}"
        if metadata is not None
        else "id: (missing)",
        *_name_lines(parse_album_name(album_dir.name)),
        *(
            [
                "media sources: "
                + ", ".join(f"{c.name} ({c.media_source_type})" for c in media_sources)
            ]
            if media_sources
            else []
        ),
    ]
    typer.echo(indent("\n".join(details)))


def _name_lines(parsed: ParsedAlbumName | None) -> list[str]:
    """Unindented ``key: value`` lines for the parsed album name."""
    if parsed is None:
        return ["(name not parseable)"]
    return [
        f"date: {parsed.date}",
        *([f"part: {parsed.part}"] if parsed.part is not None else []),
        *([f"series: {parsed.series}"] if parsed.series is not None else []),
        f"title: {parsed.title}",
        *([f"location: {parsed.location}"] if parsed.location is not None else []),
        *(["private: yes"] if parsed.private else []),
    ]
