"""The ``photree album fix-exif`` command."""

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from photree.album import exif as album_exif
from photree.album.cli.app import app
from photree.clihelpers.console import console, err_console
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.sysdeps import EXIF_DEPS, require_system_deps
from photree.clihelpers.usage import (
    exactly_one_error,
    invalid_value_error,
    mutually_exclusive_error,
    no_files_error,
)
from photree.common import exif as common_exif
from photree.common.formatting import CHECK, indent, markup_escape
from photree.common.fs import display_path


@dataclass(frozen=True)
class _SetDate:
    date: str


@dataclass(frozen=True)
class _SetDateTime:
    timestamp: str


@dataclass(frozen=True)
class _ShiftDate:
    days: int


@dataclass(frozen=True)
class _ShiftTime:
    hours: int


type _Operation = _SetDate | _SetDateTime | _ShiftDate | _ShiftTime


_DATE_PARTS = 3  # YYYY-MM-DD
_OPERATION_OPTIONS = ("--set-date", "--set-date-time", "--shift-date", "--shift-time")


def _select_operation(
    set_date: str | None,
    set_date_time: str | None,
    shift_date: int | None,
    shift_time: int | None,
) -> _Operation:
    """Turn the four mutually exclusive flags into one operation, or a usage error."""
    match (set_date, set_date_time, shift_date, shift_time):
        case (str() as date, None, None, None):
            return _SetDate(date)
        case (None, str() as timestamp, None, None):
            return _SetDateTime(timestamp)
        case (None, None, int() as days, None):
            return _ShiftDate(days)
        case (None, None, None, int() as hours):
            return _ShiftTime(hours)
        case (None, None, None, None):
            raise exactly_one_error(_OPERATION_OPTIONS)
        case _:
            raise mutually_exclusive_error(_OPERATION_OPTIONS)


def _validate_operation(operation: _Operation) -> None:
    match operation:
        case _SetDate(date):
            parts = date.split("-")
            if len(parts) != _DATE_PARTS or not all(p.isdigit() for p in parts):
                raise invalid_value_error(
                    name="date",
                    value=date,
                    expected="YYYY-MM-DD",
                )
        case _:
            pass


def _apply(operation: _Operation, files: list[Path], cwd: Path) -> tuple[str, ...]:
    """
    Run *operation* on *files*; return one result line per changed file.

    Lines are built only after exiftool succeeded, so nothing is reported as
    fixed before it actually is.
    """
    match operation:
        case _SetDate(date):
            changes = album_exif.set_exif_date(files, date)
            return tuple(
                f"fix-exif {display_path(c.path, cwd)}: {c.original} -> {c.new_value}"
                for c in changes
            )
        case _SetDateTime(timestamp):
            common_exif.set_exif_date_time(files, timestamp)
            return tuple(
                f"fix-exif {display_path(f, cwd)}: -> {timestamp}" for f in files
            )
        case _ShiftDate(days):
            common_exif.shift_exif_date(files, days)
            return tuple(
                f"fix-exif shift {days:+d}d {display_path(f, cwd)}" for f in files
            )
        case _ShiftTime(hours):
            common_exif.shift_exif_time(files, hours)
            return tuple(
                f"fix-exif shift {hours:+d}h {display_path(f, cwd)}" for f in files
            )


def _report_exiftool_error(exc: common_exif.ExifToolError, cwd: Path) -> None:
    err_console.print(f"fix-exif failed: exiftool exited with status {exc.returncode}.")
    err_console.print(
        "\n".join(indent(markup_escape(display_path(p, cwd))) for p in exc.paths),
    )
    if exc.stderr:
        err_console.print(indent(markup_escape(exc.stderr)))
    first = shlex.quote(str(display_path(exc.paths[0], cwd))) if exc.paths else "<file>"
    err_console.print(
        "Check that the files exist and are writable media files,"
        f" e.g. run 'exiftool {markup_escape(first)}'.",
    )


@app.command("fix-exif")
def fix_exif_cmd(
    ctx: typer.Context,
    *,
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
    """
    Fix EXIF dates on media files.

    Exactly one of --set-date, --set-date-time, --shift-date, or
    --shift-time must be specified.

    --set-date preserves the original time portion of each file's
    timestamp, only replacing the date.

    --set-date-time sets the full timestamp (date + time) on all files.

    --shift-date shifts all date tags by N days.

    --shift-time shifts all date tags by N hours.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    operation = _select_operation(set_date, set_date_time, shift_date, shift_time)
    if not files:
        raise no_files_error()
    _validate_operation(operation)
    require_system_deps(EXIF_DEPS, which=runtime.which)

    try:
        lines = _apply(operation, [Path(f) for f in files], cwd)
    except common_exif.ExifToolError as exc:
        _report_exiftool_error(exc, cwd)
        raise typer.Exit(code=1) from exc

    for line in lines:
        console.print(f"{CHECK} {markup_escape(line)}")
    typer.echo(f"Done. {len(lines)} file(s) updated.")
