"""The ``photree album fix`` command."""

from pathlib import Path
from typing import Annotated

import typer

from photree.album import fix as album_fixes
from photree.album.cli.app import app
from photree.album.cli.media_source_conflict import exit_on_media_source_conflict
from photree.album.fix import (
    FixValidationError,
    MissingArchiveError,
    RmUpstreamIncompleteSignalError,
    RmUpstreamRefusedError,
)
from photree.album.fix.output import format_fix_result
from photree.album.id import format_album_external_id, generate_album_id
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.clihelpers.console import err_console
from photree.clihelpers.options import (
    DRY_RUN_OPTION,
    FORCE_OPTION,
    RM_ORPHAN_OPTION,
    RM_UPSTREAM_OPTION,
)
from photree.clihelpers.paths import expand_user_path
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.usage import invalid_fix_error
from photree.common.formatting import format_dry_run, format_flags
from photree.common.fs import display_path


@app.command("fix")
def fix_cmd(
    ctx: typer.Context,
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to fix.",
            file_okay=False,
            callback=expand_user_path(exists=True),
        ),
    ] = Path(),
    *,
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
    rm_upstream: RM_UPSTREAM_OPTION = False,
    rm_orphan: RM_ORPHAN_OPTION = False,
    force: FORCE_OPTION = False,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """
    Fix album issues. Works on all media source types (iOS + std).

    --id: Generates a missing album ID in .photree/album.yaml. Skips
    albums that already have an ID.

    --new-id: Regenerates the album ID, replacing any existing one.

    --rm-upstream: Propagates deletions from browsing directories to
    upstream directories. A missing browsing directory, or an empty
    {name}-jpg/, is never taken as "everything was deleted"; a run that
    would delete every item of an archive is refused unless --force. A
    browsing directory that a failed or interrupted refresh left incomplete
    is refused even with --force: run 'photree album refresh' first.

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
        raise invalid_fix_error(exc, command="album fix") from exc

    if fix_id or new_id:
        _fix_album_id(album_dir, new_id=new_id, dry_run=dry_run)

    if rm_upstream or rm_orphan:
        _run_archive_fixes(
            album_dir,
            rm_upstream=rm_upstream,
            rm_orphan=rm_orphan,
            force=force,
            dry_run=dry_run,
            cwd=runtime_of(ctx).cwd(),
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
            typer.echo(format_dry_run("Would generate album ID.", dry_run=True))
        case _:
            generated_id = generate_album_id()
            save_album_metadata(album_dir, AlbumMetadata(id=generated_id))
            typer.echo(f"Generated album ID: {format_album_external_id(generated_id)}")


def _run_archive_fixes(
    album_dir: Path,
    *,
    rm_upstream: bool,
    rm_orphan: bool,
    force: bool,
    dry_run: bool,
    cwd: Path,
) -> None:
    with exit_on_media_source_conflict(cwd):
        try:
            result = album_fixes.run_fix(
                album_dir,
                dry_run=dry_run,
                rm_upstream_flag=rm_upstream,
                rm_orphan_flag=rm_orphan,
                force=force,
            )
        except RmUpstreamRefusedError as exc:
            err_console.print(
                f"Refusing to delete all {exc.key_count} {exc.kind} of media source "
                f'"{exc.media_source}": its browsable directory looks emptied.',
                markup=False,
            )
            retry_flags = format_flags(
                [("--rm-orphan", rm_orphan), ("--dry-run", dry_run)],
            )
            err_console.print(
                "If that deletion is intended, run 'photree album fix --rm-upstream "
                f'--force{retry_flags} --album-dir "{display_path(album_dir, cwd)}"\'.',
                markup=False,
            )
            raise typer.Exit(code=1) from exc
        except RmUpstreamIncompleteSignalError as exc:
            _print_incomplete_signal(exc, album_dir, cwd)
            raise typer.Exit(code=1) from exc
        except MissingArchiveError as exc:
            err_console.print(
                f"Archive directory {exc.archive_dir} does not exist in "
                f"{display_path(exc.album_dir, cwd)}; archive-dependent fixes "
                "cannot run without it.",
                markup=False,
            )
            raise typer.Exit(code=1) from exc

    for line in format_fix_result(result, dry_run=dry_run):
        typer.echo(line)


def _print_incomplete_signal(
    exc: RmUpstreamIncompleteSignalError,
    album_dir: Path,
    cwd: Path,
) -> None:
    dirs = ", ".join(f"{d}/" for d in exc.directories)
    err_console.print(
        f'Refusing to propagate deletions from media source "{exc.media_source}": '
        f"the last refresh failed or was interrupted while writing {dirs}, so the "
        "files missing there are not deletions.",
        markup=False,
    )
    err_console.print(
        f"Run 'photree album refresh --album-dir \"{display_path(album_dir, cwd)}\"' "
        "first, then delete again any file it restores that you meant to remove.",
        markup=False,
    )
