"""``photree album fix`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import album_app
from .helpers import _check_sips_or_exit
from .. import (
    fixes as album_fixes,
    output as album_output,
)
from ...clicommons.options import (
    DRY_RUN_OPTION,
    REFRESH_JPEG_OPTION,
)
from ...clicommons.progress import FileProgressBar
from ...fs import (
    AlbumMetadata,
    discover_media_sources,
    format_album_external_id,
    generate_album_id,
    list_files,
    load_album_metadata,
    save_album_metadata,
)


@album_app.command("fix")
def fix_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to fix.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    fix_id: Annotated[
        bool,
        typer.Option(
            "--id",
            help="Generate missing album ID (.photree/album.yaml).",
        ),
    ] = False,
    new_id: Annotated[
        bool,
        typer.Option(
            "--new-id",
            help="Regenerate album ID (replaces existing ID).",
        ),
    ] = False,
    refresh_jpeg: REFRESH_JPEG_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix album issues. Works on all msutor types (iOS + plain).

    --id: Generates a missing album ID in .photree/album.yaml. Skips
    albums that already have an ID.

    --new-id: Regenerates the album ID, replacing any existing one.

    --refresh-jpeg: Deletes all files in {msutor}-jpg/ and re-converts
    every file from {msutor}-img/. HEIC/HEIF/DNG files are converted
    via sips; JPEG/PNG files are copied as-is.
    """
    if not fix_id and not new_id and not refresh_jpeg:
        typer.echo(
            "No fix specified. Run photree album fix --help for available fixes.",
            err=True,
        )
        raise typer.Exit(code=1)

    if fix_id or new_id:
        metadata = load_album_metadata(album_dir)
        match (metadata, new_id, dry_run):
            case (AlbumMetadata() as m, False, _):
                typer.echo(f"Album already has an ID: {format_album_external_id(m.id)}")
            case (_, _, True):
                typer.echo("[dry-run] Would generate album ID.")
            case _:
                generated_id = generate_album_id()
                save_album_metadata(album_dir, AlbumMetadata(id=generated_id))
                typer.echo(
                    f"Generated album ID: {format_album_external_id(generated_id)}"
                )

    if refresh_jpeg:
        _check_sips_or_exit()
        media_sources = discover_media_sources(album_dir)
        if not media_sources:
            typer.echo("No media_sources found in this album.", err=True)
            raise typer.Exit(code=1)

        file_count = sum(
            len(list_files(album_dir / c.img_dir))
            for c in media_sources
            if (album_dir / c.img_dir).is_dir()
        )
        progress = FileProgressBar(
            total=file_count,
            description="Converting JPEG",
            done_description="convert-jpeg",
        )
        total_converted = 0
        total_copied = 0
        total_skipped = 0
        for ms in media_sources:
            if not (album_dir / ms.img_dir).is_dir():
                continue
            prefix = f"{ms.img_dir}/"
            result = album_fixes.refresh_jpeg(
                album_dir,
                ms,
                dry_run=dry_run,
                on_file_start=lambda name, p=prefix: progress.on_start(f"{p}{name}"),
                on_file_end=lambda name, ok, p=prefix: progress.on_end(
                    f"{p}{name}", ok
                ),
            )
            total_converted += result.converted
            total_copied += result.copied
            total_skipped += result.skipped
        progress.stop()
        typer.echo(
            album_output.refresh_jpeg_summary(
                total_converted, total_copied, total_skipped
            )
        )
