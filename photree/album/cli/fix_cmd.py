"""``photree album fix`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import err_console
from ...clihelpers.options import (
    DRY_RUN_OPTION,
    FORCE_OPTION,
    LINK_MODE_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from ...common.fs import display_path
from ...fsprotocol import LinkMode, resolve_link_mode
from .. import fix as album_fixes
from ..fix import FixValidationError, MissingArchiveError, RmUpstreamRefusedError
from ..fix.output import format_fix_result
from ..id import format_album_external_id, generate_album_id
from ..store.metadata import load_album_metadata, save_album_metadata
from ..store.protocol import AlbumMetadata
from . import album_app
from .helpers import exit_on_media_source_conflict


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
    force: FORCE_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Fix album issues. Works on all media source types (iOS + std).

    --id: Generates a missing album ID in .photree/album.yaml. Skips
    albums that already have an ID.

    --new-id: Regenerates the album ID, replacing any existing one.

    --rm-upstream: Propagates deletions from browsing directories to
    upstream directories. A missing browsing directory, or an empty
    {name}-jpg/, is never taken as "everything was deleted"; a run that
    would delete every item of an archive is refused unless --force.

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
        err_console.print(str(exc))
        err_console.print("Run 'photree album fix --help' to see the available fixes.")
        raise typer.Exit(code=1) from exc

    if fix_id or new_id:
        _fix_album_id(album_dir, new_id=new_id, dry_run=dry_run)

    if rm_upstream or rm_orphan:
        _run_archive_fixes(
            album_dir,
            link_mode=link_mode,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
            force=force,
            dry_run=dry_run,
        )


def _fix_album_id(album_dir: Path, *, new_id: bool, dry_run: bool) -> None:
    # A corrupt album.yaml raises InvalidMetadataError here (reported by the
    # CLI entry point) instead of being treated as missing: minting a new ID
    # over it would orphan every collection reference to the album.
    metadata = load_album_metadata(album_dir)
    match (metadata, new_id, dry_run):
        case (AlbumMetadata() as m, False, _):
            typer.echo(f"Album already has an ID: {format_album_external_id(m.id)}")
        case (_, _, True):
            typer.echo("[dry-run] Would generate album ID.")
        case _:
            generated_id = generate_album_id()
            save_album_metadata(album_dir, AlbumMetadata(id=generated_id))
            typer.echo(f"Generated album ID: {format_album_external_id(generated_id)}")


def _run_archive_fixes(
    album_dir: Path,
    *,
    link_mode: LinkMode | None,
    rm_upstream: bool,
    rm_orphan: bool,
    force: bool,
    dry_run: bool,
) -> None:
    cwd = Path.cwd()
    with exit_on_media_source_conflict(cwd):
        try:
            result = album_fixes.run_fix(
                album_dir,
                link_mode=resolve_link_mode(link_mode, album_dir),
                dry_run=dry_run,
                rm_upstream_flag=rm_upstream,
                rm_orphan_flag=rm_orphan,
                force=force,
            )
        except RmUpstreamRefusedError as exc:
            err_console.print(
                f"Refusing to delete all {exc.key_count} {exc.kind} of media source "
                f'"{exc.media_source}": its browsable directory looks emptied.'
            )
            err_console.print(
                "If that deletion is intended, run 'photree album fix --rm-upstream "
                f'--force --album-dir "{display_path(album_dir, cwd)}"\'.'
            )
            raise typer.Exit(code=1) from exc
        except MissingArchiveError as exc:
            err_console.print(
                f"Archive directory {exc.archive_dir} does not exist in "
                f"{display_path(exc.album_dir, cwd)}; archive-dependent fixes "
                "cannot run without it."
            )
            raise typer.Exit(code=1) from exc

    for line in format_fix_result(result):
        typer.echo(line)
