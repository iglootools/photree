"""``photree album fix`` command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.options import (
    DRY_RUN_OPTION,
    LINK_MODE_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from ...fsprotocol import resolve_link_mode
from .. import fix as album_fixes
from ..fix import FixValidationError
from ..fix.output import format_fix_result
from ..store.metadata import load_album_metadata, save_album_metadata
from ..id import format_album_external_id, generate_album_id
from ..store.protocol import AlbumMetadata
from . import album_app


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
    link_mode: LINK_MODE_OPTION = None,
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix album issues. Works on all media source types (iOS + std).

    --id: Generates a missing album ID in .photree/album.yaml. Skips
    albums that already have an ID.

    --new-id: Regenerates the album ID, replacing any existing one.

    --rm-upstream: Propagates deletions from browsing directories to
    upstream directories.

    --rm-orphan: Deletes edited and main files whose key has no
    corresponding original file in orig-img/ or orig-vid/.
    """
    try:
        album_fixes.validate_fix_flags(
            fix_id=fix_id,
            new_id=new_id,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
        )
    except FixValidationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

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

    any_archive_op = rm_upstream or rm_orphan
    if not any_archive_op:
        return

    result = album_fixes.run_fix(
        album_dir,
        link_mode=resolve_link_mode(link_mode, album_dir),
        dry_run=dry_run,
        rm_upstream_flag=rm_upstream,
        rm_orphan_flag=rm_orphan,
        max_workers=os.cpu_count(),
    )

    for line in format_fix_result(result):
        typer.echo(line)
