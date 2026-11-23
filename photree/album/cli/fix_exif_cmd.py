"""The ``photree album fix-exif`` command."""

import shlex
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import typer

from photree.album import exif as album_exif
from photree.album.cli.app import app
from photree.clihelpers.console import console, err_console
from photree.clihelpers.options import DRY_RUN_OPTION
from photree.clihelpers.runtime import runtime_of
from photree.clihelpers.sysdeps import EXIF_DEPS, require_system_deps
from photree.clihelpers.usage import (
    exactly_one_error,
    invalid_value_error,
    mutually_exclusive_error,
    no_files_error,
)
from photree.common import exif as common_exif
from photree.common.exif import ExifDateChange
from photree.common.formatting import CHECK, format_dry_run, indent, markup_escape
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


def _plan(operation: _Operation, files: list[Path]) -> tuple[ExifDateChange, ...]:
    """Read *files* and return what *operation* would change, writing nothing."""
    match operation:
        case _SetDate(date):
            return album_exif.plan_exif_date(files, date)
        case _SetDateTime(timestamp):
            return album_exif.plan_exif_date_time(files, timestamp)
        case _ShiftDate(days):
            return album_exif.plan_exif_shift(files, timedelta(days=days))
        case _ShiftTime(hours):
            return album_exif.plan_exif_shift(files, timedelta(hours=hours))


def _write(
    operation: _Operation,
    files: list[Path],
    changes: tuple[ExifDateChange, ...],
) -> None:
    """Run *operation*: per-file values for --set-date, one exiftool call otherwise."""
    match operation:
        case _SetDate():
            common_exif.write_exif_date_changes(changes)
        case _SetDateTime(timestamp):
            common_exif.set_exif_date_time(files, timestamp)
        case _ShiftDate(days):
            common_exif.shift_exif_date(files, days)
        case _ShiftTime(hours):
            common_exif.shift_exif_time(files, hours)


def _format_change(change: ExifDateChange, cwd: Path, *, dry_run: bool) -> str:
    """Return the Rich markup line reporting one file's date change."""
    original = change.original if change.original is not None else "(no date)"
    text = markup_escape(
        f"fix-exif {display_path(change.path, cwd)}: {original} -> {change.new_value}",
    )
    return (
        format_dry_run(f"Would {text}", dry_run=True, markup=True)
        if dry_run
        else f"{CHECK} {text}"
    )


def _format_summary(count: int, *, dry_run: bool) -> str:
    """Return the closing line: how many files were, or would be, updated."""
    return (
        format_dry_run(f"{count} file(s) would be updated.", dry_run=True)
        if dry_run
        else f"Done. {count} file(s) updated."
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
    dry_run: DRY_RUN_OPTION = False,
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

    Each changed file is listed with its date before and after;
    --dry-run lists them without writing.
    """
    runtime = runtime_of(ctx)
    cwd = runtime.cwd()
    operation = _select_operation(set_date, set_date_time, shift_date, shift_time)
    if not files:
        raise no_files_error()
    _validate_operation(operation)
    require_system_deps(EXIF_DEPS, which=runtime.which)

    paths = [Path(f) for f in files]
    try:
        # Lines are printed only after exiftool succeeded, so nothing is
        # reported as fixed before it actually is.
        changes = _plan(operation, paths)
        if not dry_run:
            _write(operation, paths, changes)
    except common_exif.ExifToolError as exc:
        _report_exiftool_error(exc, cwd)
        raise typer.Exit(code=1) from exc

    for change in changes:
        console.print(_format_change(change, cwd, dry_run=dry_run))
    console.print(_format_summary(len(changes), dry_run=dry_run), markup=False)
