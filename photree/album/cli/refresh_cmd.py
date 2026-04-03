"""``photree album refresh`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...common.fs import display_path
from ...fsprotocol import PHOTREE_DIR
from ..refresh import refresh_media_metadata
from ..store.protocol import MEDIA_YAML
from . import album_app


@album_app.command("refresh")
def refresh_cmd(
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
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would change without writing."),
    ] = False,
) -> None:
    """Refresh media metadata (.photree/media.yaml) — assign IDs to new media."""
    cwd = Path.cwd()
    result = refresh_media_metadata(album_dir, dry_run=dry_run)

    if not result.by_media_source:
        typer.echo("No media sources with archives found.")
        raise typer.Exit(code=0)

    media_yaml = album_dir / PHOTREE_DIR / MEDIA_YAML
    if dry_run:
        typer.echo(f"[dry run] Would write {display_path(media_yaml, cwd)}")
    else:
        typer.echo(f"Refreshed {display_path(media_yaml, cwd)}")

    for ms_name, ms_result in result.by_media_source:
        parts = [
            f"{ms_result.new_images} new image(s)",
            f"{ms_result.new_videos} new video(s)",
        ]
        if ms_result.removed_images or ms_result.removed_videos:
            parts.append(
                f"{ms_result.removed_images + ms_result.removed_videos} removed"
            )
        typer.echo(f"  {ms_name}: {', '.join(parts)}")
