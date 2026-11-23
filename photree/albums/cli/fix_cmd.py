"""The ``photree albums fix`` command."""

from typing import Annotated

import typer

from photree.album.fix import FixValidationError, validate_fix_flags
from photree.albums.batchcli.fix import run_batch_fix
from photree.albums.batchcli.resolution import resolve_check_batch_albums
from photree.albums.cli.app import app
from photree.albums.cli.options import ALBUM_DIR_OPTION, DIR_OPTION
from photree.clihelpers.options import (
    DRY_RUN_OPTION,
    FORCE_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import invalid_fix_error, usage_error

_NEW_ID_NEEDS_ALBUM_DIRS = (
    "--new-id needs the albums named with --album-dir: a new ID orphans every "
    "collection and face reference to the album, so it never runs on a scan.\n"
    "Run 'photree albums fix --new-id --album-dir <album>' for each album that "
    "needs a new ID."
)


@app.command("fix")
def fix_cmd(
    ctx: typer.Context,
    base_dir: DIR_OPTION = None,
    album_dirs: ALBUM_DIR_OPTION = None,
    *,
    fix_id: Annotated[
        bool,
        typer.Option("--id", help="Generate missing album IDs (.photree/album.yaml)."),
    ] = False,
    new_id: Annotated[
        bool,
        typer.Option(
            "--new-id",
            help=(
                "Regenerate the IDs of the albums named with --album-dir "
                "(replaces existing IDs). Refused on a --dir scan."
            ),
        ),
    ] = False,
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    force: FORCE_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """
    Fix all albums under a directory or from an explicit list.

    --new-id runs only on albums named with --album-dir: a new ID orphans every
    collection and face reference to the album, so it never applies to every
    album a scan finds.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    try:
        validate_fix_flags(
            fix_id=fix_id,
            new_id=new_id,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
        )
    except FixValidationError as exc:
        raise invalid_fix_error(exc, command="albums fix") from exc
    if new_id and not album_dirs:
        raise usage_error(_NEW_ID_NEEDS_ALBUM_DIRS, markup=False)

    albums, display_base = resolve_check_batch_albums(base_dir, album_dirs, cwd=cwd)

    run_batch_fix(
        albums,
        display_base,
        fix_id=fix_id,
        new_id=new_id,
        rm_upstream=rm_upstream,
        rm_orphan=rm_orphan,
        dry_run=dry_run,
        force=force,
        cwd=cwd,
    )
