"""``photree album optimize`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import console, err_console
from ...clihelpers.options import (
    CHECK_BEFORE_OPTION,
    CHECKSUM_OPTION,
    DRY_RUN_OPTION,
    LINK_MODE_OPTION,
)
from ...clihelpers.progress import SilentProgressBar
from ...common.fs import count_unique_media_numbers, display_path
from ...gallery.store.fs import resolve_link_mode
from .. import (
    optimize as album_optimize,
)
from .. import (
    preflight as album_preflight,
)
from ..preflight import output as preflight_output
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import IMG_EXTENSIONS, VID_EXTENSIONS
from . import album_app


@album_app.command("optimize")
def optimize_cmd(
    album_dir: Annotated[
        Path,
        typer.Option(
            "--album-dir",
            "-a",
            help="Album directory to optimize.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    link_mode: LINK_MODE_OPTION = None,
    check: CHECK_BEFORE_OPTION = True,
    checksum: CHECKSUM_OPTION = True,
    dry_run: DRY_RUN_OPTION = False,
) -> None:
    """Optimize main directories by replacing file copies with links.

    Recreates main-img/ and main-vid/ files as hard links (default),
    symbolic links, or copies depending on --link-mode. Does not touch
    main-jpg/ (those are HEIC-to-JPEG conversions that cannot be linked).

    Runs structural integrity checks first (unless --no-check): directory
    structure, file matching, checksums, sidecars, duplicates, and
    miscategorized files. Naming and EXIF checks are not performed.
    Refuses to optimize if errors are found.
    """
    if check:
        # Run checks first
        file_count = sum(
            count_unique_media_numbers(album_dir / c.orig_img_dir, IMG_EXTENSIONS)
            + count_unique_media_numbers(album_dir / c.orig_vid_dir, VID_EXTENSIONS)
            for c in discover_media_sources(album_dir)
        )
        progress = (
            SilentProgressBar(total=max(file_count, 1), description="Checking")
            if file_count > 0
            else None
        )

        check_result = album_preflight.run_album_preflight(
            album_dir,
            checksum=checksum,
            on_file_checked=progress.advance if progress else None,
        )
        if progress:
            progress.stop()

        console.print(preflight_output.format_album_preflight_checks(check_result))

        if not check_result.success:
            cwd = Path.cwd()
            troubleshoot = preflight_output.format_album_preflight_troubleshoot(
                check_result, album_dir=str(display_path(album_dir, cwd))
            )
            if troubleshoot:
                typer.echo("")
                err_console.print(troubleshoot)
            raise typer.Exit(code=1)

    # Optimize
    resolved_link_mode = resolve_link_mode(link_mode, album_dir)
    result = album_optimize.optimize_album(
        album_dir, link_mode=resolved_link_mode, dry_run=dry_run
    )
    typer.echo(
        album_optimize.optimize_summary(
            result.heic_count, result.mov_count, resolved_link_mode
        )
    )
