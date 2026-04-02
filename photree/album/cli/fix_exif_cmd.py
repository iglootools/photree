"""``photree album fix-exif`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ...clihelpers.console import err_console
from ...common import exif as common_exif
from .. import exif as album_exif
from . import album_app


@album_app.command("fix-exif")
def fix_exif_cmd(
    set_date: Annotated[
        str | None,
        typer.Option(
            "--set-date",
            help="Set EXIF date to YYYY-MM-DD (preserves original time).",
        ),
    ] = None,
    set_date_time: Annotated[
        str | None,
        typer.Option(
            "--set-date-time",
            help="Set EXIF date+time to an ISO timestamp (e.g. 2024-07-20T13:55:20).",
        ),
    ] = None,
    shift_date: Annotated[
        int | None,
        typer.Option(
            "--shift-date",
            help="Shift EXIF date by N days (e.g. -1, +2).",
        ),
    ] = None,
    shift_time: Annotated[
        int | None,
        typer.Option(
            "--shift-time",
            help="Shift EXIF time by N hours (e.g. -6, +3).",
        ),
    ] = None,
    files: Annotated[
        list[str],
        typer.Argument(
            help="File paths to fix (relative from cwd).",
        ),
    ] = [],  # noqa: B006
) -> None:
    """Fix EXIF dates on media files.

    Exactly one of --set-date, --set-date-time, --shift-date, or
    --shift-time must be specified.

    --set-date preserves the original time portion of each file's
    timestamp, only replacing the date.

    --set-date-time sets the full timestamp (date + time) on all files.

    --shift-date shifts all date tags by N days.

    --shift-time shifts all date tags by N hours.
    """
    flags = sum(
        x is not None for x in (set_date, set_date_time, shift_date, shift_time)
    )
    if flags == 0:
        err_console.print(
            "Specify exactly one of --set-date, --set-date-time,"
            " --shift-date, or --shift-time."
        )
        raise typer.Exit(code=1)
    if flags > 1:
        err_console.print(
            "--set-date, --set-date-time, --shift-date, and --shift-time"
            " are mutually exclusive."
        )
        raise typer.Exit(code=1)
    if not files:
        err_console.print("No files specified.")
        raise typer.Exit(code=1)

    if set_date is not None:
        parts = set_date.split("-")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            err_console.print(f'Invalid date "{set_date}", expected YYYY-MM-DD.')
            raise typer.Exit(code=1)

    cwd = Path.cwd()
    file_paths = [Path(f) for f in files]

    from ...clihelpers.console import console, log_action
    from ...common.formatting import CHECK
    from ...common.fs import display_path

    if set_date is not None:
        updated, changes = album_exif.set_exif_date(file_paths, set_date)
        for change in changes:
            console.print(
                f"{CHECK} fix-exif {display_path(change.path, cwd)}: {change.original} -> {change.new_value}"
            )
    elif set_date_time is not None:
        log = log_action()
        for f in file_paths:
            log(f"fix-exif {display_path(f, cwd)}: -> {set_date_time}")
        updated = common_exif.set_exif_date_time(file_paths, set_date_time)
    elif shift_date is not None:
        log = log_action()
        sign = "+" if shift_date >= 0 else ""
        for f in file_paths:
            log(f"fix-exif shift {sign}{shift_date}d {display_path(f, cwd)}")
        updated = common_exif.shift_exif_date(file_paths, shift_date)
    else:
        assert shift_time is not None
        log = log_action()
        sign = "+" if shift_time >= 0 else ""
        for f in file_paths:
            log(f"fix-exif shift {sign}{shift_time}h {display_path(f, cwd)}")
        updated = common_exif.shift_exif_time(file_paths, shift_time)

    typer.echo(f"Done. {updated} file(s) updated.")
