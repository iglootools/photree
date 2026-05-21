"""``photree gallery list-collections`` command."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import gallery_app
from ...collection.id import format_collection_external_id
from ...collection.naming import parse_collection_name
from ...collection.store.collection_discovery import discover_collections
from ...collection.store.metadata import load_collection_metadata
from ...fsprotocol import COLLECTIONS_DIR
from .ops import resolve_gallery_or_exit


def _display_name(col_dir: Path, gallery_dir: Path, cwd: Path) -> str:
    return str(col_dir.relative_to(gallery_dir))


@gallery_app.command("list-collections")
def list_collections_cmd(
    gallery_dir: Annotated[
        Optional[Path],
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
    """List all collections in the gallery."""
    resolved = resolve_gallery_or_exit(gallery_dir)
    cwd = Path.cwd()
    collections = discover_collections(resolved / COLLECTIONS_DIR)

    if not collections:
        typer.echo("No collections found.", err=output_format == "csv")
        raise typer.Exit(code=0)

    if output_format == "csv":
        _list_csv(collections, resolved, cwd, output_file)
    else:
        _list_text(collections, resolved, cwd, metadata)


def _list_csv(
    collections: list[Path],
    gallery_dir: Path,
    cwd: Path,
    output_file: Path | None,
) -> None:
    out = (
        open(output_file, "w", encoding="utf-8", newline="")
        if output_file
        else sys.stdout
    )
    try:
        writer = csv.writer(out)
        writer.writerow(
            [
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
        )
        for col_dir in collections:
            rel_path = _display_name(col_dir, gallery_dir, cwd)
            col_meta = load_collection_metadata(col_dir)
            external_id = (
                format_collection_external_id(col_meta.id)
                if col_meta is not None
                else ""
            )
            parsed = parse_collection_name(col_dir.name)

            writer.writerow(
                [
                    external_id,
                    rel_path,
                    parsed.date or "",
                    parsed.title,
                    parsed.location or "",
                    "private" if parsed.private else "",
                    col_meta.members.value if col_meta is not None else "",
                    col_meta.lifecycle.value if col_meta is not None else "",
                    col_meta.strategy.value if col_meta is not None else "",
                    len(col_meta.albums) if col_meta is not None else 0,
                    len(col_meta.collections) if col_meta is not None else 0,
                    len(col_meta.images) if col_meta is not None else 0,
                    len(col_meta.videos) if col_meta is not None else 0,
                ]
            )
    finally:
        if output_file:
            out.close()


def _list_text(
    collections: list[Path],
    gallery_dir: Path,
    cwd: Path,
    show_metadata: bool,
) -> None:
    typer.echo(f"Found {len(collections)} collection(s).\n")

    for col_dir in collections:
        name = _display_name(col_dir, gallery_dir, cwd)
        typer.echo(name)

        if show_metadata:
            col_meta = load_collection_metadata(col_dir)
            if col_meta is not None:
                typer.echo(f"  id: {format_collection_external_id(col_meta.id)}")
                typer.echo(f"  members: {col_meta.members}")
                typer.echo(f"  lifecycle: {col_meta.lifecycle}")
                typer.echo(f"  strategy: {col_meta.strategy}")
            else:
                typer.echo("  id: (missing)")

            parsed = parse_collection_name(col_dir.name)
            parts = [
                *([f"date={parsed.date}"] if parsed.date is not None else []),
                f"title={parsed.title}",
                *(
                    [f"location={parsed.location}"]
                    if parsed.location is not None
                    else []
                ),
                *(["private"] if parsed.private else []),
            ]
            typer.echo(f"  {', '.join(parts)}")

            if col_meta is not None:
                member_parts = [
                    *([f"albums={len(col_meta.albums)}"] if col_meta.albums else []),
                    *(
                        [f"collections={len(col_meta.collections)}"]
                        if col_meta.collections
                        else []
                    ),
                    *([f"images={len(col_meta.images)}"] if col_meta.images else []),
                    *([f"videos={len(col_meta.videos)}"] if col_meta.videos else []),
                ]
                if member_parts:
                    typer.echo(f"  members: {', '.join(member_parts)}")
