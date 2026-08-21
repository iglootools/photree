"""``albums list`` / ``gallery list-albums`` wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ....album.id import format_album_external_id
from ....album.store.media_sources_discovery import discover_media_sources
from ....album.store.metadata import load_album_metadata
from ....clihelpers.console import err_console
from ....common.fs import display_path
from ..ops import display_name


def run_batch_list_albums(
    albums: list[Path],
    display_base: Path | None,
    *,
    metadata: bool = True,
    output_format: str = "text",
    output_file: Path | None = None,
) -> None:
    """Shared implementation for list-albums / albums list."""
    import csv

    from ....album.naming import parse_album_name
    from ....clihelpers.csvout import csv_output

    cwd = Path.cwd()

    if not albums:
        typer.echo("No albums found.", err=output_format == "csv")
        raise typer.Exit(code=0)

    # All albums must have IDs
    missing_id = [a for a in albums if load_album_metadata(a) is None]
    if missing_id:
        err_console.print("Albums with missing IDs found:")
        for p in missing_id:
            err_console.print(f"  {display_path(p, cwd)}")
        err_console.print(
            "\nRun 'photree gallery fix --id' to generate missing album IDs."
        )
        raise typer.Exit(code=1)

    if output_format == "csv":
        with csv_output(output_file) as out:
            writer = csv.writer(out)
            writer.writerow(
                [
                    "id",
                    "path",
                    "date",
                    "part",
                    "series",
                    "title",
                    "location",
                    "tags",
                    "media_sources",
                ]
            )
            for album_dir in albums:
                rel_path = display_name(album_dir, display_base, cwd)
                album_meta = load_album_metadata(album_dir)
                external_id = (
                    format_album_external_id(album_meta.id)
                    if album_meta is not None
                    else ""
                )
                parsed = parse_album_name(album_dir.name)
                media_sources = discover_media_sources(album_dir)
                ms_desc = ", ".join(
                    f"{c.name} ({c.media_source_type})" for c in media_sources
                )
                if parsed is not None:
                    tags = "private" if parsed.private else ""
                    writer.writerow(
                        [
                            external_id,
                            rel_path,
                            parsed.date,
                            parsed.part or "",
                            parsed.series or "",
                            parsed.title,
                            parsed.location or "",
                            tags,
                            ms_desc,
                        ]
                    )
                else:
                    writer.writerow(
                        [
                            external_id,
                            rel_path,
                            "",
                            "",
                            "",
                            album_dir.name,
                            "",
                            "",
                            ms_desc,
                        ]
                    )
        return

    typer.echo(f"Found {len(albums)} album(s).\n")

    for album_dir in albums:
        name = display_name(album_dir, display_base, cwd)
        typer.echo(name)

        if metadata:
            album_meta = load_album_metadata(album_dir)
            if album_meta is not None:
                typer.echo(f"  id: {format_album_external_id(album_meta.id)}")
            else:
                typer.echo("  id: (missing)")

            parsed = parse_album_name(album_dir.name)
            media_sources = discover_media_sources(album_dir)

            if parsed is not None:
                parts = [f"date={parsed.date}"]
                if parsed.part is not None:
                    parts.append(f"part={parsed.part}")
                if parsed.series is not None:
                    parts.append(f"series={parsed.series}")
                parts.append(f"title={parsed.title}")
                if parsed.location is not None:
                    parts.append(f"location={parsed.location}")
                if parsed.private:
                    parts.append("private")
                typer.echo(f"  {', '.join(parts)}")
            else:
                typer.echo("  (name not parseable)")

            if media_sources:
                ms_desc = ", ".join(
                    f"{c.name} ({c.media_source_type})" for c in media_sources
                )
                typer.echo(f"  media sources: {ms_desc}")
