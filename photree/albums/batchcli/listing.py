"""``albums list`` / ``gallery list-albums`` wrapper."""

from __future__ import annotations

from pathlib import Path

import typer

from ...album.id import format_album_external_id
from ...album.naming import ParsedAlbumName, parse_album_name
from ...album.store.media_sources_discovery import discover_media_sources
from ...album.store.metadata import load_album_metadata
from ...album.store.protocol import AlbumMetadata
from ...clihelpers.console import err_console
from ...clihelpers.options import OutputFormat
from ...common.formatting import indent
from ...common.fs import display_path
from .resolution import display_name
from .sink import write_csv, write_text

_CSV_HEADER = (
    "id",
    "path",
    "date",
    "part",
    "series",
    "title",
    "location",
    "tags",
    "media_sources",
)


def _media_sources_desc(album_dir: Path) -> str:
    return ", ".join(
        f"{c.name} ({c.media_source_type})" for c in discover_media_sources(album_dir)
    )


def _require_ids(
    albums: list[Path], display_base: Path | None, cwd: Path
) -> dict[Path, AlbumMetadata]:
    """Load every album's metadata, exiting with a fix suggestion if any lacks one."""
    metas = {album: load_album_metadata(album) for album in albums}
    found = {album: meta for album, meta in metas.items() if meta is not None}
    missing = [album for album in albums if album not in found]
    if missing:
        target = (
            f'--dir "{display_path(display_base, cwd)}"'
            if display_base is not None
            else " ".join(f'--album-dir "{display_path(a, cwd)}"' for a in missing)
        )
        err_console.print(
            "\n".join(
                [
                    "Albums with missing IDs found:",
                    *(indent(str(display_path(p, cwd))) for p in missing),
                    (
                        f"\nRun 'photree albums fix --id {target}' to generate "
                        "missing album IDs."
                    ),
                ]
            ),
            markup=False,
        )
        raise typer.Exit(code=1)
    return found


def _csv_row(album_dir: Path, meta: AlbumMetadata, name: str) -> list[str]:
    parsed = parse_album_name(album_dir.name)
    fields = (
        [
            parsed.date,
            parsed.part or "",
            parsed.series or "",
            parsed.title,
            parsed.location or "",
            "private" if parsed.private else "",
        ]
        if parsed is not None
        else ["", "", "", album_dir.name, "", ""]
    )
    return [
        format_album_external_id(meta.id),
        name,
        *fields,
        _media_sources_desc(album_dir),
    ]


def _parsed_summary(parsed: ParsedAlbumName) -> str:
    return ", ".join(
        [
            f"date={parsed.date}",
            *([f"part={parsed.part}"] if parsed.part is not None else []),
            *([f"series={parsed.series}"] if parsed.series is not None else []),
            f"title={parsed.title}",
            *([f"location={parsed.location}"] if parsed.location is not None else []),
            *(["private"] if parsed.private else []),
        ]
    )


def _text_details(album_dir: Path, meta: AlbumMetadata) -> list[str]:
    """Unindented metadata lines for one album."""
    parsed = parse_album_name(album_dir.name)
    ms_desc = _media_sources_desc(album_dir)
    return [
        f"id: {format_album_external_id(meta.id)}",
        _parsed_summary(parsed) if parsed is not None else "(name not parseable)",
        *([f"media sources: {ms_desc}"] if ms_desc else []),
    ]


def _text_lines(
    metas: dict[Path, AlbumMetadata], names: dict[Path, str], *, metadata: bool
) -> list[str]:
    return [
        f"Found {len(metas)} album(s).\n",
        *(
            line
            for album_dir, meta in metas.items()
            for line in [
                names[album_dir],
                *(
                    indent(d)
                    for d in (_text_details(album_dir, meta) if metadata else [])
                ),
            ]
        ),
    ]


def run_batch_list_albums(
    albums: list[Path],
    display_base: Path | None,
    *,
    metadata: bool = True,
    output_format: OutputFormat = OutputFormat.TEXT,
    output_file: Path | None = None,
) -> None:
    """Shared implementation for list-albums / albums list.

    *output_file* applies to both formats.
    """
    cwd = Path.cwd()
    if not albums:
        typer.echo("No albums found.", err=output_format == OutputFormat.CSV)
        raise typer.Exit(code=0)

    metas = _require_ids(albums, display_base, cwd)
    names = {album: display_name(album, display_base, cwd) for album in albums}
    match output_format:
        case OutputFormat.CSV:
            rows = (_csv_row(a, meta, names[a]) for a, meta in metas.items())
            write_csv(_CSV_HEADER, rows, output_file)
        case OutputFormat.TEXT:
            write_text(_text_lines(metas, names, metadata=metadata), output_file)
