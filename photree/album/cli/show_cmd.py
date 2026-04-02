"""``photree album show`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...common.fs import display_path
from ..naming import parse_album_name
from ..store.media_sources_discovery import discover_media_sources
from ..store.metadata import load_album_metadata
from ..store.protocol import format_album_external_id
from . import album_app


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
    typer.echo(f"Album: {display_path(album_dir, cwd)}")
    typer.echo(f"  directory: {album_dir.name}")

    metadata = load_album_metadata(album_dir)
    if metadata is not None:
        typer.echo(f"  id: {format_album_external_id(metadata.id)}")
    else:
        typer.echo("  id: (missing)")

    parsed = parse_album_name(album_dir.name)
    if parsed is not None:
        typer.echo(f"  date: {parsed.date}")
        if parsed.part is not None:
            typer.echo(f"  part: {parsed.part}")
        if parsed.series is not None:
            typer.echo(f"  series: {parsed.series}")
        typer.echo(f"  title: {parsed.title}")
        if parsed.location is not None:
            typer.echo(f"  location: {parsed.location}")
        if parsed.private:
            typer.echo("  private: yes")
    else:
        typer.echo("  (name not parseable)")

    media_sources = discover_media_sources(album_dir)
    if media_sources:
        ms_desc = ", ".join(f"{c.name} ({c.media_source_type})" for c in media_sources)
        typer.echo(f"  media sources: {ms_desc}")
