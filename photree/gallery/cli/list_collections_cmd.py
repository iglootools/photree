"""``photree gallery list-collections`` command."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import err_console
from ...clihelpers.csvout import csv_output
from ...clihelpers.options import (
    OUTPUT_FILE_OPTION,
    OUTPUT_FORMAT_OPTION,
    OutputFormat,
)
from ...clihelpers.resolution import resolve_gallery_or_exit
from ...collection.id import format_collection_external_id
from ...collection.naming import ParsedCollectionName, parse_collection_name
from ...collection.store.collection_discovery import discover_collections
from ...collection.store.metadata import load_collection_metadata
from ...collection.store.protocol import CollectionMetadata
from ...common.formatting import indent
from ...common.fs import display_path
from ...fsprotocol import COLLECTIONS_DIR
from . import gallery_app

_CSV_HEADER = [
    "id",
    "path",
    "date",
    "title",
    "location",
    "tags",
    "members",
    "lifecycle",
    "strategy",
    "albums",
    "collections",
    "images",
    "videos",
]


@gallery_app.command("list-collections")
def list_collections_cmd(
    gallery_dir: Annotated[
        Path | None,
        typer.Option(
            "--gallery-dir",
            "-d",
            help="Gallery root directory (or resolved from cwd via .photree/gallery.yaml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = None,
    metadata: Annotated[
        bool,
        typer.Option(
            "--metadata/--no-metadata",
            help="Show parsed collection metadata (default: enabled).",
        ),
    ] = True,
    output_format: OUTPUT_FORMAT_OPTION = OutputFormat.TEXT,
    output_file: OUTPUT_FILE_OPTION = None,
) -> None:
    """List all collections in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()
    collections = discover_collections(resolved / COLLECTIONS_DIR)

    match output_format, collections:
        case OutputFormat.CSV, []:
            # Keep stdout pure CSV: the notice goes to stderr.
            err_console.print("No collections found.")
        case OutputFormat.TEXT, []:
            typer.echo("No collections found.")
        case OutputFormat.CSV, _:
            _list_csv(collections, cwd, output_file)
        case OutputFormat.TEXT, _:
            _list_text(collections, cwd, metadata)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _member_counts(meta: CollectionMetadata | None) -> list[int]:
    return (
        [len(meta.albums), len(meta.collections), len(meta.images), len(meta.videos)]
        if meta is not None
        else [0, 0, 0, 0]
    )


def _csv_row(col_dir: Path, cwd: Path) -> list[str | int]:
    meta = load_collection_metadata(col_dir)
    parsed = parse_collection_name(col_dir.name)
    return [
        format_collection_external_id(meta.id) if meta is not None else "",
        str(display_path(col_dir, cwd)),
        parsed.date or "",
        parsed.title,
        parsed.location or "",
        "private" if parsed.private else "",
        *(
            [meta.members.value, meta.lifecycle.value, meta.strategy.value]
            if meta is not None
            else ["", "", ""]
        ),
        *_member_counts(meta),
    ]


def _list_csv(collections: list[Path], cwd: Path, output_file: Path | None) -> None:
    with csv_output(output_file) as out:
        writer = csv.writer(out)
        writer.writerow(_CSV_HEADER)
        writer.writerows(_csv_row(col_dir, cwd) for col_dir in collections)


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


def _name_line(parsed: ParsedCollectionName) -> str:
    return ", ".join(
        [
            *([f"date={parsed.date}"] if parsed.date is not None else []),
            f"title={parsed.title}",
            *([f"location={parsed.location}"] if parsed.location is not None else []),
            *(["private"] if parsed.private else []),
        ]
    )


def _metadata_lines(meta: CollectionMetadata | None) -> list[str]:
    return (
        [
            f"id: {format_collection_external_id(meta.id)}",
            f"members: {meta.members}",
            f"lifecycle: {meta.lifecycle}",
            f"strategy: {meta.strategy}",
        ]
        if meta is not None
        else ["id: (missing)"]
    )


def _member_count_parts(meta: CollectionMetadata | None) -> list[str]:
    return (
        [
            f"{label}={len(ids)}"
            for label, ids in (
                ("albums", meta.albums),
                ("collections", meta.collections),
                ("images", meta.images),
                ("videos", meta.videos),
            )
            if ids
        ]
        if meta is not None
        else []
    )


def _text_block(col_dir: Path, cwd: Path, show_metadata: bool) -> str:
    """The collection's path, then (optionally) its indented metadata."""
    if not show_metadata:
        return str(display_path(col_dir, cwd))
    meta = load_collection_metadata(col_dir)
    member_counts = _member_count_parts(meta)
    details = [
        *_metadata_lines(meta),
        _name_line(parse_collection_name(col_dir.name)),
        *([f"members: {', '.join(member_counts)}"] if member_counts else []),
    ]
    return "\n".join([str(display_path(col_dir, cwd)), *(indent(d) for d in details)])


def _list_text(collections: list[Path], cwd: Path, show_metadata: bool) -> None:
    typer.echo(f"Found {len(collections)} collection(s).\n")
    typer.echo("\n".join(_text_block(c, cwd, show_metadata) for c in collections))
